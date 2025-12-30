import os
from msal import ConfidentialClientApplication


def get_msal_app():
    client_id = os.environ.get('AZURE_CLIENT_ID')
    client_secret = os.environ.get('AZURE_CLIENT_SECRET')
    authority = os.environ.get('AZURE_AUTHORITY')
    if not client_id or not client_secret or not authority:
        return None
    return ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
