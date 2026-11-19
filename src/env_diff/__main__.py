"""Allow ``python -m env_diff`` when the console script is not on PATH."""

import sys

from env_diff.cli import main

sys.exit(main())
