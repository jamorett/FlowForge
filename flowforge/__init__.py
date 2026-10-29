"""FlowForge v2 package."""

from flowforge.env import load_dotenv as _load_dotenv

# Load project .env (MODEL_API_KEY, MODEL_API_BASE, FLOWFORGE_SAM_ENDPOINT)
# once per process. Real environment variables always win; nothing is
# logged. Absence of a .env file is fine.
_load_dotenv()
