from pathlib import Path
import sys

# Also support an absolute script path in native hooks without shell activation.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native_remediation.cli import main

if __name__ == "__main__":
    main()
