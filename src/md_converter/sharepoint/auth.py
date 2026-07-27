import msal


class GraphAuth:
    """Acquires Microsoft Graph tokens using the OAuth2 client-credentials (app-only) flow.

    No user sign-in is involved: the app authenticates as itself with a client secret.
    The registered app must hold the required Graph *application* permission on the
    target sites (see README — ``Sites.Selected`` is recommended).
    """

    _SCOPES = ["https://graph.microsoft.com/.default"]

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )

    def token(self) -> str:
        # MSAL caches the token internally and only calls the network when it is
        # missing or near expiry, so this is cheap to call before every request.
        result = self._app.acquire_token_for_client(scopes=self._SCOPES)
        if "access_token" not in result:
            raise RuntimeError(
                "Failed to acquire a Microsoft Graph token "
                f"({result.get('error')}): {result.get('error_description')}"
            )
        return result["access_token"]
