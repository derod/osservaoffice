import os
from google_auth_oauthlib.flow import Flow

# 🔥 Esto soluciona el error de HTTPS en local
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

flow = Flow.from_client_secrets_file(
    "credentials.json",
    scopes=SCOPES,
    redirect_uri="http://localhost:8000/oauth2callback",
)

auth_url, state = flow.authorization_url(
    access_type="offline",
    include_granted_scopes="true",
    prompt="consent",
)

print("\nOpen this URL in your browser:\n")
print(auth_url)
print()

full_redirect = input("Paste the FULL redirected URL here:\n").strip()

flow.fetch_token(authorization_response=full_redirect)

with open("token.json", "w", encoding="utf-8") as f:
    f.write(flow.credentials.to_json())

print("\n✅ token.json created successfully\n")