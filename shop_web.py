from flask import Flask, render_template_string
import requests

app = Flask(__name__)

# ─── AUTH ───────────────────────────────────────────
def get_tokens(username, password):
    session = requests.Session()
    session.post("https://auth.riotgames.com/api/v1/authorization", json={
        "client_id": "play-valorant-web-prod",
        "nonce": "1",
        "redirect_uri": "https://playvalorant.com/opt_in",
        "response_type": "token id_token",
        "scope": "account openid"
    })
    resp = session.put("https://auth.riotgames.com/api/v1/authorization", json={
        "type": "auth",
        "username": username,
        "password": password
    }).json()
    uri = resp["response"]["parameters"]["uri"]
    access_token = uri.split("access_token=")[1].split("&")[0]
    entitlement = session.post(
        "https://entitlements.auth.riotgames.com/api/token/v1",
        headers={"Authorization": f"Bearer {access_token}"},
        json={}
    ).json()["entitlements_token"]
    puuid = session.get(
        "https://auth.riotgames.com/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()["sub"]
    return session, access_token, entitlement, puuid

def get_store(session, access_token, entitlement, puuid, region="ap"):
    resp = session.get(
        f"https://pd.{region}.a.pvp.net/store/v2/storefront/{puuid}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Riot-Entitlements-JWT": entitlement,
            "X-Riot-ClientVersion": "release-09.00.00.2008642"
        }
    ).json()
    skin_uuids = resp["SkinsPanelLayout"]["SingleItemOffers"]
    price_map = {}
    for offer in resp["SkinsPanelLayout"]["SingleItemStoreOffers"]:
        uid = offer["OfferID"]
        vp = offer["Cost"].get("85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741", 0)
        price_map[uid] = vp
    return skin_uuids, price_map

def get_skin_data(uuid):
    resp = requests.get(f"https://valorant-api.com/v1/weapons/skinlevels/{uuid}").json()
    data = resp["data"]
    return data["displayName"], data.get("displayIcon", "")

# ─── HTML TEMPLATE ───────────────────────────────────
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Val Shop</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0f1923; color: white; font-family: sans-serif; padding: 20px; }
    h1 { color: #ff4655; text-align: center; margin-bottom: 20px; font-size: 1.4rem; }
    .card {
      background: #1f2a35;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .card img { width: 90px; height: 90px; object-fit: contain; }
    .info { flex: 1; }
    .name { font-size: 1rem; font-weight: bold; margin-bottom: 6px; }
    .price { color: #00e4ff; font-size: 0.9rem; }
    form { text-align: center; margin-bottom: 30px; }
    input {
      display: block; width: 100%; padding: 10px;
      margin: 8px 0; border-radius: 8px;
      border: none; background: #1f2a35; color: white; font-size: 1rem;
    }
    button {
      background: #ff4655; color: white; border: none;
      padding: 12px 30px; border-radius: 8px;
      font-size: 1rem; cursor: pointer; margin-top: 8px;
    }
  </style>
</head>
<body>
  <h1>🛒 Valorant Daily Shop</h1>
  {% if not skins %}
  <form method="POST">
    <input name="username" placeholder="Riot Username" required>
    <input name="password" type="password" placeholder="Password" required>
    <input name="region" placeholder="Region (ap / na / eu)" value="ap">
    <button type="submit">ดู Shop</button>
  </form>
  {% else %}
  {% for skin in skins %}
  <div class="card">
    <img src="{{ skin.icon }}" onerror="this.style.display='none'">
    <div class="info">
      <div class="name">{{ skin.name }}</div>
      <div class="price">💰 {{ skin.price }} VP</div>
    </div>
  </div>
  {% endfor %}
  {% endif %}
</body>
</html>
"""

# ─── ROUTES ─────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    skins = []
    if requests.request.__module__ and hasattr(requests, 'post'):
        from flask import request as freq
        if freq.method == "POST":
            username = freq.form["username"]
            password = freq.form["password"]
            region = freq.form.get("region", "ap")
            try:
                session, token, entitlement, puuid = get_tokens(username, password)
                uuids, prices = get_store(session, token, entitlement, puuid, region)
                for uuid in uuids:
                    name, icon = get_skin_data(uuid)
                    skins.append({"name": name, "price": prices.get(uuid, "?"), "icon": icon})
            except Exception as e:
                skins = [{"name": f"Error: {e}", "price": "-", "icon": ""}]
    return render_template_string(TEMPLATE, skins=skins)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)