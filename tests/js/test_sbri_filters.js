#!/usr/bin/env node
/* Behavioral test for the embedded, dependency-free SBRI table controls.
 * Usage: NODE_PATH=/path/to/node_modules node tests/js/test_sbri_filters.js report.html
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require('jsdom');

const htmlPath = process.argv[2];
if (!htmlPath) throw new Error('report.html path is required');
const dom = new JSDOM(fs.readFileSync(htmlPath, 'utf8'), {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'file:///sbri-report.html'
});
const {window} = dom; const {document} = window;
const click = element => element.dispatchEvent(new window.MouseEvent('click', {bubbles: true}));
const visibleRows = table => Array.from(table.tBodies[0].rows).filter(row => !row.hidden);
const status = table => table.closest('.table-region').querySelector('.row-count').textContent;

function open(table, column) {
  click(table.querySelectorAll('.filter-button')[column]);
  return document.querySelector('.filter-menu');
}
function choose(menu, values) {
  click(menu.querySelector('[data-select="none"]'));
  menu.querySelectorAll('.filter-value').forEach(label => {
    if (values.includes(label.textContent.trim())) label.querySelector('input').checked = true;
  });
  click(menu.querySelector('[data-action="apply"]'));
}

const tables = Array.from(document.querySelectorAll('table[data-filterable]'));
assert.equal(tables.length, 4, 'the frozen report still has exactly four tables');
assert.equal(document.querySelectorAll('.filter-button').length, 34, 'every header has a filter button');
document.querySelectorAll('.filter-button').forEach(button => {
  assert.match(button.getAttribute('aria-label'), /^Filter and sort /);
  assert.equal(button.getAttribute('aria-haspopup'), 'dialog');
});

// Search distinct text values, select one, and verify visible/total counts.
const table3 = document.querySelector('#table3');
let menu = open(table3, 0);
click(menu.querySelector('[data-select="none"]'));
const search = menu.querySelector('.filter-search'); search.value = 'commons-text';
search.dispatchEvent(new window.Event('input', {bubbles: true}));
assert.equal(Array.from(menu.querySelectorAll('.filter-value')).filter(x => !x.hidden).length, 1);
click(menu.querySelector('[data-select="all"]'));
click(menu.querySelector('[data-action="apply"]'));
assert.equal(visibleRows(table3).length, 1);
assert.equal(status(table3), 'Showing 1 of 62 rows');
assert.match(visibleRows(table3)[0].cells[0].textContent, /commons-text/);
assert.ok(table3.querySelectorAll('.filter-button')[0].classList.contains('active'));
menu = open(table3, 0); click(menu.querySelector('[data-action="clear"]'));
assert.equal(visibleRows(table3).length, 62);

// Multiple values in one column use OR; another column combines with AND.
const table4 = document.querySelector('#table4');
menu = open(table4, 1);
choose(menu, ['BOOT_MANAGED', 'OTHER_BOM_PARENT_MANAGED']);
assert.equal(visibleRows(table4).length, 58);
menu = open(table4, 8);
choose(menu, ['Remains']);
assert.ok(visibleRows(table4).length > 0 && visibleRows(table4).length < 58);
assert.ok(visibleRows(table4).every(row =>
  ['BOOT_MANAGED', 'OTHER_BOM_PARENT_MANAGED'].includes(row.cells[1].textContent.trim()) &&
  row.cells[8].textContent.trim() === 'Remains'));

// Numeric sorting is numeric, stable, and applies to the current visible rows.
const table1 = document.querySelector('#table1');
menu = open(table1, 6); click(menu.querySelector('[data-sort="asc"]'));
assert.deepEqual(visibleRows(table1).map(row => Number(row.cells[6].textContent)), [12, 17, 50]);
menu = open(table1, 6); click(menu.querySelector('[data-sort="desc"]'));
assert.deepEqual(visibleRows(table1).map(row => Number(row.cells[6].textContent)), [50, 17, 12]);
assert.equal(table1.tBodies[0].rows[0].cells[1].textContent.trim(), '4.0.6 (Base)');

// Severity labels remain labels and support multi-selection.
const table2 = document.querySelector('#table2');
menu = open(table2, 1); choose(menu, ['Critical', 'High']);
assert.equal(visibleRows(table2).length, 6);
assert.ok(visibleRows(table2).every(row => ['Critical', 'High'].includes(row.cells[1].textContent.trim())));

// Reset is per table and restores its original stable order and count.
click(table1.closest('.table-region').querySelector('.reset-filters'));
assert.equal(status(table1), 'Showing 3 of 3 rows');
assert.equal(table1.tBodies[0].rows[0].cells[1].textContent.trim(), '4.0.6 (Base)');

// Candidate switching uses retained data, rebuilds values, and drops stale filters/sort.
const selector = document.querySelector('select[onchange]');
selector.value = '4.0.7'; selector.dispatchEvent(new window.Event('change', {bubbles: true}));
assert.equal(visibleRows(table4).length, 62);
assert.equal(status(table4), 'Showing 62 of 62 rows');
assert.equal(table4.tHead.rows[0].cells[3].querySelector('.header-label').textContent,
             'Boot 4.0.7 default');
assert.equal(table4.querySelectorAll('.filter-button.active').length, 0);

// Escape and outside-click close behavior; buttons remain keyboard-addressable.
menu = open(table2, 0);
assert.ok(menu); menu.dispatchEvent(new window.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
assert.equal(document.querySelector('.filter-menu'), null);
menu = open(table2, 0); click(document.body);
assert.equal(document.querySelector('.filter-menu'), null);

console.log(JSON.stringify({
  status: 'PASS', tables: 4, filter_buttons: 34,
  checks: ['search', 'checkbox OR', 'combined AND', 'numeric sort', 'severity filter',
           'reset', 'row counts', 'release switch', 'state reset', 'escape', 'outside click',
           'accessible labels', 'frozen values']
}, null, 2));
