from flask import Flask, render_template_string, request, session
import requests
import json

app = Flask(__name__)
app.secret_key = "valshopsecret2026"

# ─── TEMPLATES ──────────────────────────────────────
BASE_STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0f1923; color: white; font-family: sans-serif; padding: 20px; }
h1 { color: #ff4655; text-align: center; margin-bottom: 24px; font-size: 1.4rem; }
input {
  display: block; width: 100%; padding: 12px;
  margin: 10px 0; border-radius: 8px;
  border: none; background: #1f2a35; color: white; font-size: 1rem;
}
button {
  width: 100%; background: #ff4655; color: white; border: none;
  padding: 13px; border-radius: 8px; font-size: 1rem; cursor: pointer; margin-top: 8px;
}
.card {
  background: #1f2a35; border-radius: 12px;
  padding: 16px; margin-bottom: 16px;
  display: flex; align-items: center; gap: 16px;
}
.card img { width: 90px; height: 90px; object-fit: contain; }
.name { font-size: 1rem; font-weight: bold; margin-bottom: 6px; }
.price { color: #00e4ff; font-size: 0.9rem; }
.error { background: #2a1f1f; border-radius: 8px; padding: 12px; color: #ff6b6b; margin-bottom: 16px; }
.wrap { max-width: 480px; margin: 0 auto; }
</style>
"""

LOGIN_TMPL = """
<!DOCTYPE html><html><head>{style}</head><body>
<div class="wrap">
  <h1>🛒 Valorant Daily Shop</h1>
  {error}
  <form method="POST">
    <input name="username" placeholder="Riot Username" required>
    <input name="password" type="password" placeholder="Password" required>
    <input name="region" value="ap" placeholder="Region (ap/na/eu)">
    <button type="submit">เข้าสู่ระบบ</button>
  </form>
</div></body></html>
"""

MFA_TMPL = """
<!DOCTYPE html><html><head>{style}</head><body>
<div class="wrap">
  <h1>🔐 Two-Factor Auth</h1>
  {error}
  <p style="text-align:center;margin-bottom:16px;color:#aaa">กรอก code จาก email หรือ authenticator</p>
  <form method="POST" action="/verify">
    <input name="code" placeholder="6-digit code" maxlength="6" required autofocus
    style="text-align:center;font-size:1.4rem;letter-spacing:8px">
    <button type="submit">ยืนยัน</button>
  </form>
</div></body></html>
"""

SHOP_TMPL = """
<!DOCTYPE html><html><head>{style}</head><body>
<div class="wrap">
  <h1>🛒 Daily Shop</h1>
  {cards}
  <form method="POST" action="/logout" style="margin-top:20px">
    <button style="background:#1f2a35">ออกจากระบบ</button>
  </form>
</div></body></html>
"""

# ─── AUTH ───────────────────────────────────────────
def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "RiotClient/60.0.6.4770705.4749685 rso-auth/2 (Windows;10;;Professional, x64)",
        "Content-Type": "application/json"
    })
    return s

def init_auth(s):
    s.post("https://auth.riotgames.com/api/v1/authorization", json={
        "client_id": "play-valorant-web-prod",
        "nonce": "1",
        "redirect_uri": "https://playvalorant.com/opt_in",
        "response_type": "token id_token",
        "scope": "account openid"
    })

def extract_token(uri):
    return uri.split("access_token=")[1].split("&")[0]

def finish_auth(s, access_token):
    entitlement = s.post(
        "https://entitlements.auth.riotgames.com/api/token/v1",
        headers={"Authorization": f"Bearer {access_token}"},
        json={}
    ).json()["entitlements_token"]

    puuid = s.get(
        "https://auth.riotgames.com/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()["sub"]

    return entitlement, puuid

def get_store(s, access_token, entitlement, puuid, region):
    resp = s.get(
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

# ─── ROUTES ─────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    error = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        region = request.form.get("region", "ap")

        try:
            s = make_session()
            init_auth(s)

            resp = s.put("https://auth.riotgames.com/api/v1/authorization", json={
                "type": "auth",
                "username": username,
                "password": password,
                "remember": False
            }).json()

            if resp.get("type") == "error":
                raise Exception("username หรือ password ไม่ถูกต้อง")

            elif resp.get("type") == "multifactor":
                # เก็บ cookies + region ไว้ใน session
                session["cookies"] = dict(s.cookies)
                session["region"] = region
                return render_template_string(
                    MFA_TMPL.format(style=BASE_STYLE, error="")
                )

            elif resp.get("type") == "response":
                access_token = extract_token(resp["response"]["parameters"]["uri"])
                entitlement, puuid = finish_auth(s, access_token)
                uuids, prices = get_store(s, access_token, entitlement, puuid, region)
                return show_shop(uuids, prices)

            else:
                raise Exception(f"Unexpected: {resp}")

        except Exception as e:
            error = f'<div class="error">⚠️ {e}</div>'

    return render_template_string(LOGIN_TMPL.format(style=BASE_STYLE, error=error))


@app.route("/verify", methods=["POST", "GET"])
def verify():
    cookies = session.get("cookies", {})
    region = session.get("region", "ap")
    
    # แสดงหน้า "รออนุมัติบนมือถือ"
    return render_template_string("""
    <!DOCTYPE html><html><head>{style}
    <script>
      // poll ทุก 3 วินาที
      async function poll() {{
        const res = await fetch('/poll');
        const data = await res.json();
        if (data.status === 'ok') {{
          window.location.href = '/shop_result';
        }} else if (data.status === 'error') {{
          document.getElementById('msg').innerText = '❌ ' + data.msg;
        }} else {{
          setTimeout(poll, 3000);
        }}
      }}
      window.onload = () => setTimeout(poll, 3000);
    </script>
    </head><body>
    <div class="wrap" style="text-align:center;margin-top:80px">
      <h1>📱 รออนุมัติ</h1>
      <p style="color:#aaa;margin:20px 0">กดอนุมัติในแอป Riot บนมือถือของคุณ</p>
      <div style="font-size:2rem;margin:20px 0">⏳</div>
      <p id="msg" style="color:#ff6b6b"></p>
    </div></body></html>
    """.format(style=BASE_STYLE))


@app.route("/poll")
def poll():
    cookies = session.get("cookies", {})
    region = session.get("region", "ap")
    
    try:
        s = make_session()
        s.cookies.update(cookies)
        
        resp = s.get(
            "https://auth.riotgames.com/api/v1/authorization"
        ).json()
        
        if resp.get("type") == "response":
            access_token = extract_token(resp["response"]["parameters"]["uri"])
            entitlement, puuid = finish_auth(s, access_token)
            uuids, prices = get_store(s, access_token, entitlement, puuid, region)
            
            # เก็บผลไว้ใน session
            skins = []
            for uuid in uuids:
                name, icon = get_skin_data(uuid)
                skins.append({"name": name, "icon": icon, "price": prices.get(uuid, "?")})
            session["skins"] = skins
            
            return {"status": "ok"}
        
        elif resp.get("type") == "multifactor":
            return {"status": "waiting"}
        
        else:
            return {"status": "error", "msg": str(resp)}
    
    except Exception as e:
        return {"status": "error", "msg": str(e)}


@app.route("/shop_result")
def shop_result():
    skins = session.get("skins", [])
    cards = ""
    for skin in skins:
        img = f'<img src="{skin["icon"]}" onerror="this.style.display=\'none\'">' if skin["icon"] else ""
        cards += f"""
        <div class="card">
          {img}
          <div>
            <div class="name">{skin["name"]}</div>
            <div class="price">💰 {skin["price"]} VP</div>
          </div>
        </div>"""
    return render_template_string(SHOP_TMPL.format(style=BASE_STYLE, cards=cards))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return index()


def show_shop(uuids, prices):
    cards = ""
    for uuid in uuids:
        name, icon = get_skin_data(uuid)
        price = prices.get(uuid, "?")
        img = f'<img src="{icon}" onerror="this.style.display=\'none\'">' if icon else ""
        cards += f"""
        <div class="card">
          {img}
          <div>
            <div class="name">{name}</div>
            <div class="price">💰 {price} VP</div>
          </div>
        </div>"""
    return render_template_string(SHOP_TMPL.format(style=BASE_STYLE, cards=cards))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)