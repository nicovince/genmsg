# Add current folder in module search path.
# This let slip module import messages, when slip is imported from a script elsewhere
# Note: Maybe not the ideal way of using __init__.py...
import sys
sys.path.append("genmsg")
