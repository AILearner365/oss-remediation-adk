"""Automated Maven-only remediation tool for the ADK OSS workflow."""
from __future__ import annotations
import json, os, re, shlex
from pathlib import Path
from typing import Any
from oss_remediation_agent.tools.scanner_tools import CRITICAL_HIGH,_extract_vulnerabilities,_run,_run_osv,_trim,_version_key
B=("clean","install"); T=("test",)

def generate_remediation_report(vulnerability_assessment_report:dict[str,Any], workspace_path:str|None=None)->dict[str,Any]:
    a=vulnerability_assessment_report or {}; repo=Path(workspace_path or a.get("workspacePath") or ".").resolve(); r=_report(a,repo)
    vulns=[v for v in a.get("vulnerabilities",[]) if str(v.get("severity","")).upper() in CRITICAL_HIGH]
    if a.get("buildStatus")!="SUCCESS": r["failedItems"].append(_fail("Agent 1 buildStatus is not SUCCESS.")); return r
    if not repo.exists(): r["failedItems"].append(_fail(f"Workspace path not found: {repo}")); return r
    if a.get("featureBranch"):
        x=_run(["git","checkout","-B",a["featureBranch"]],repo)
        if x["returncode"]: r["failedItems"].append(_fail("Cannot checkout remediation branch.",x)); return r
    snap=_snap(repo); orig={_k(v) for v in vulns}
    for v in vulns:
        it=_one(repo,v,orig); r[{"FIXED":"remediatedVulnerabilities","MANUAL_REVIEW":"manualReviewItems"}.get(it["status"],"failedItems")].append(it)
    if r["failedItems"]: _restore(snap); return r
    r["modifiedFiles"]=_changed(repo,snap)
    for key,env,goals in (("buildStatus","OSS_REMEDIATION_BUILD_GOALS",B),("testStatus","OSS_REMEDIATION_TEST_GOALS",T)):
        x=_mvn(repo,_goals(env,goals)); r[key]="SUCCESS" if x["returncode"]==0 else "FAILED"
        if x["returncode"]: _restore(snap); r["modifiedFiles"]=[]; r["failedItems"].append(_fail(f"{key} failed after remediation.",x)); return r
    rem=_extract_vulnerabilities(_run_osv(repo).get("json") or {}); man={_k(v) for v in r["manualReviewItems"]}
    items=[{"dependencyName":v.get("dependencyName"),"severity":v.get("severity"),"vulnerabilityIds":v.get("vulnerabilityIds",[]),"status":"MANUAL_REVIEW" if _k(v) in man else "UNRESOLVED"} for v in rem]
    r["postRemediationScan"]={"criticalRemaining":sum(i["severity"]=="CRITICAL" for i in items),"highRemaining":sum(i["severity"]=="HIGH" for i in items),"newCriticalOrHighIntroduced":any(_k(v) not in orig for v in rem),"remainingCriticalOrHighItems":items}
    bad=[i for i in items if i["status"]!="MANUAL_REVIEW"]
    if bad or r["postRemediationScan"]["newCriticalOrHighIntroduced"]: r["failedItems"].extend(bad); r["remediationStatus"]="FAILED"
    elif r["manualReviewItems"]: r["remediationStatus"]="PARTIAL_SUCCESS"
    else: r["remediationStatus"]="SUCCESS"
    return r

def apply_remediation(repo_url,dependency,recommended_version):
    return {"status":"manual_review","repo_url":repo_url,"dependency":dependency,"requested_version":recommended_version,"message":"Use generate_remediation_report with Agent 1's report."}

def _report(a,repo):
    return {"repositoryUrl":a.get("repositoryUrl"),"referenceBranch":a.get("referenceBranch"),"featureBranch":a.get("featureBranch"),"remediationStatus":"FAILED","buildStatus":"NOT_RUN","testStatus":"NOT_RUN","workspacePath":str(repo),"modifiedFiles":[],"remediatedVulnerabilities":[],"manualReviewItems":[],"failedItems":[],"postRemediationScan":{"criticalRemaining":0,"highRemaining":0,"newCriticalOrHighIntroduced":False,"remainingCriticalOrHighItems":[]}}

def _one(repo,v,orig):
    dep=str(v.get("dependencyName") or ""); p=dep.split(":"); fixes=sorted({str(x) for x in v.get("suggestedFixVersions",[]) if x},key=_version_key)
    if len(p)<2: return _manual(v,f"Not a Maven coordinate: {dep}")
    if not fixes: return _manual(v,"No suggested fixed versions from OSV.")
    if re.search(r"\b(jdk|java)\s*(17|21|22|23)\b|requires?\s+(jdk|java)|minimum\s+(jdk|java)",json.dumps(v,default=str).lower()): return _manual(v,"Fix appears to require JDK/Java upgrade, out of scope.")
    targets=_find_targets(repo,p[0],p[1],str(v.get("affectedPomFile") or "pom.xml"),bool(v.get("isDirectDependency")))
    if not targets: return _manual(v,"No safe Maven version target found; external parent or non-version build change may be required.")
    base=_snap(repo); attempts=[]
    for ver in fixes:
      for t in targets:
        _restore(base); u=_apply_target(t,ver)
        if not u["updated"]: attempts.append({"version":ver,"target":_lbl(t),"reason":u["reason"]}); continue
        ok,why=_ok(repo,v,orig)
        if not ok: attempts.append({"version":ver,"target":_lbl(t),"reason":why}); continue
        pom=str(t[0].relative_to(repo)); return {"dependencyName":dep,"previousVersion":v.get("currentVersion"),"updatedVersion":ver,"severity":str(v.get("severity","")).upper(),"vulnerabilityIds":v.get("vulnerabilityIds",[]),"affectedPomFile":pom,"suggestedFixVersions":fixes,"selectedVersionReason":_why(ver,t),"rejectedVersions":[{"version":x,"reason":_rej(x,ver,attempts)} for x in fixes if x!=ver],"status":"FIXED","modifiedFiles":[pom],"updateStrategy":t[1]}
    _restore(base); return _manual(v,"No suggested fixed version passed build, tests, and OSV validation.",attempts)

def _ok(repo,v,orig):
    for env,goals in (("OSS_REMEDIATION_BUILD_GOALS",B),("OSS_REMEDIATION_TEST_GOALS",T)):
        x=_mvn(repo,_goals(env,goals))
        if x["returncode"]: return False,_jdk_fail(x) or "Build/tests failed for candidate."
    rem=_extract_vulnerabilities(_run_osv(repo).get("json") or {}); keys={_k(x) for x in rem}
    if _k(v) in keys: return False,"OSV still reports original vulnerability."
    if any(_k(x) not in orig for x in rem): return False,"Candidate introduced new Critical/High vulnerability."
    return True,""

def _find_targets(repo,g,a,affected,direct):
    out=[]
    for managed in (False,True):
      for pom in _poms(repo,affected): out+=_existing(pom,g,a,managed)
    if not out and not direct and _tree(repo,g,a) and (repo/"pom.xml").exists(): out.append((repo/"pom.xml","dependencyManagementOverride",g,a,None,True))
    return _dedupe(out)

def _poms(repo,affected):
    out=[]
    for p in [(repo/affected).resolve() if affected else repo/"pom.xml",repo/"pom.xml",*sorted(repo.rglob("pom.xml"))]:
        try:p.relative_to(repo)
        except ValueError:continue
        if p.exists() and p.name=="pom.xml" and p not in out: out.append(p)
    return out

def _existing(pom,g,a,want):
    text=_read(pom); out=[]; ranges=_ranges(text)
    for m in re.finditer(r"<dependency\b[^>]*>.*?</dependency>",text,re.DOTALL):
        b=m.group(0); managed=any(s<=m.start()<=e for s,e in ranges)
        if managed!=want or _tag(b,"groupId")!=g or _tag(b,"artifactId")!=a: continue
        v=_tag(b,"version")
        if not v: continue
        prop=re.fullmatch(r"\$\{([^}]+)\}",v.strip())
        if prop and _has(text,prop.group(1)): out.append((pom,"propertyVersion",g,a,prop.group(1),managed))
        elif not prop: out.append((pom,"dependencyVersion",g,a,None,managed))
    return out

def _apply_target(t,ver):
    return _replace_tag(t[0],t[4],ver) if t[1]=="propertyVersion" else _replace_dep(t[0],t[2],t[3],ver,t[5]) if t[1]=="dependencyVersion" else _insert_dependency_management_override(t[0],t[2],t[3],ver) if t[1]=="dependencyManagementOverride" else {"updated":False,"reason":"Unknown target"}

def _replace_tag(pom,tag,val):
    text=_read(pom); pat=re.compile(rf"(<{re.escape(tag)}\b[^>]*>)(.*?)(</{re.escape(tag)}>)",re.DOTALL)
    if not pat.search(text): return {"updated":False,"reason":f"Tag {tag} not found."}
    _write(pom,pat.sub(lambda m:f"{m.group(1)}{val}{m.group(3)}",text,1)); return {"updated":True,"reason":None}

def _replace_dep(pom,g,a,ver,want):
    text=_read(pom); ranges=_ranges(text)
    for m in re.finditer(r"<dependency\b[^>]*>.*?</dependency>",text,re.DOTALL):
        b=m.group(0); managed=any(s<=m.start()<=e for s,e in ranges)
        if managed!=want or _tag(b,"groupId")!=g or _tag(b,"artifactId")!=a: continue
        if not re.search(r"<version\b[^>]*>.*?</version>",b,re.DOTALL): return {"updated":False,"reason":"No direct version tag."}
        nb=re.sub(r"(<version\b[^>]*>)(.*?)(</version>)",lambda x:f"{x.group(1)}{ver}{x.group(3)}",b,1,flags=re.DOTALL); _write(pom,text[:m.start()]+nb+text[m.end():]); return {"updated":True,"reason":None}
    return {"updated":False,"reason":"Dependency declaration not found."}

def _insert_dependency_management_override(pom,g,a,ver):
    text=_read(pom); nl="\r\n" if "\r\n" in text else "\n"; im=re.search(r"\n(\s*)<dependencies\b",text); i=im.group(1) if im else "  "
    dep=f"{i*3}<dependency>{nl}{i*4}<groupId>{g}</groupId>{nl}{i*4}<artifactId>{a}</artifactId>{nl}{i*4}<version>{ver}</version>{nl}{i*3}</dependency>{nl}"; dm=re.search(r"<dependencyManagement\b[^>]*>.*?<dependencies\b[^>]*>",text,re.DOTALL)
    if dm:
        at=text.find("</dependencies>",dm.end())
        if at<0: return {"updated":False,"reason":"Malformed dependencyManagement."}
        _write(pom,text[:at]+dep+text[at:]); return {"updated":True,"reason":None}
    at=text.find("</project>")
    if at<0: return {"updated":False,"reason":"No </project> insertion point."}
    _write(pom,text[:at]+f"{i}<dependencyManagement>{nl}{i*2}<dependencies>{nl}{dep}{i*2}</dependencies>{nl}{i}</dependencyManagement>{nl}"+text[at:]); return {"updated":True,"reason":None}

def _mvn(repo,goals): return _run(["./mvnw" if (repo/"mvnw").exists() else "mvn","-B",*shlex.split(os.getenv("OSS_REMEDIATION_MAVEN_ARGS","")),*goals],repo,timeout=1800)
def _goals(env,default): return shlex.split(os.getenv(env,"")) or list(default)
def _tree(repo,g,a):
    x=_mvn(repo,["dependency:tree",f"-Dincludes={g}:{a}"]); return x["returncode"]==0 and f"{g}:{a}" in f"{x.get('stdout','')}\n{x.get('stderr','')}"
def _tag(b,t):
    m=re.search(rf"<{t}\b[^>]*>(.*?)</{t}>",b,re.DOTALL); return re.sub(r"\s+"," ",m.group(1)).strip() if m else None
def _ranges(text): return [(m.start(),m.end()) for m in re.finditer(r"<dependencyManagement\b[^>]*>.*?</dependencyManagement>",text,re.DOTALL)]
def _has(text,name): return bool(re.search(rf"<{re.escape(name)}\b[^>]*>.*?</{re.escape(name)}>",text,re.DOTALL))
def _manual(v,reason,attempts=None):
    x={"dependencyName":v.get("dependencyName"),"currentVersion":v.get("currentVersion"),"severity":str(v.get("severity","")).upper(),"vulnerabilityIds":v.get("vulnerabilityIds",[]),"suggestedFixVersions":v.get("suggestedFixVersions",[]),"affectedPomFile":v.get("affectedPomFile"),"status":"MANUAL_REVIEW","manualReviewRequired":True,"manualReviewReason":reason}
    if attempts:x["attemptedVersions"]=attempts
    return x
def _fail(reason,out=None): return {"status":"FAILED","reason":reason,**({"details":_trim(out)} if out else {})}
def _jdk_fail(x):
    text=f"{x.get('stdout','')}\n{x.get('stderr','')}".lower(); return "Candidate fixed version appears to require a JDK upgrade, which is out of scope." if any(s in text for s in ["invalid target release","release version","unsupported class file major version","compiled by a more recent version","source release","target release"]) else None
def _read(p): return p.read_bytes().decode("utf-8")
def _write(p,text): p.write_bytes(text.encode("utf-8"))
def _snap(repo): return {p:_read(p) for p in repo.rglob("pom.xml")}
def _restore(snap):
    for p,c in snap.items(): _write(p,c)
def _changed(repo,snap): return sorted(str(p.relative_to(repo)) for p,c in snap.items() if p.exists() and _read(p)!=c)
def _dedupe(ts):
    seen=set(); out=[]
    for t in ts:
        k=(t[0],t[1],t[4],t[5])
        if k not in seen: seen.add(k); out.append(t)
    return out
def _lbl(t): return f"{t[0]}:{t[1]}:{t[4] or t[2]+':'+t[3]}"
def _why(v,t): return f"Selected {v} after build, test, and OSV validation; updated Maven {t[1]} without source-code or JDK changes."
def _rej(x,sel,attempts):
    for a in attempts:
        if a.get("version")==x: return str(a.get("reason") or "Rejected during validation.")
    return f"Not selected because {sel} was the lowest suggested version that passed validation."
def _k(item): return str(item.get("dependencyName") or ""),tuple(sorted(str(v) for v in item.get("vulnerabilityIds",[])))
