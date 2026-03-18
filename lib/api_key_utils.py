import os


def get_api_azure_api_key_for_grok():
    key = os.environ.get("AZUREAI_API_KEY")
    if not key:
        raise ValueError("AZUREAI_API_KEY environment variable not set")
    return key
