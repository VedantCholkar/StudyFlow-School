import json
import os
import sqlite3
import datetime


from flask import Flask, redirect, request, url_for, render_template
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from oauthlib.oauth2 import WebApplicationClient
import requests

from db import init_db_command, get_db
from user import User
from cal_setup import get_calendar_service


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)


login_manager = LoginManager()
login_manager.init_app(app)

try:
    init_db_command()
except sqlite3.OperationalError:
    pass

client = WebApplicationClient(GOOGLE_CLIENT_ID)


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@app.route("/")
def index():
    if current_user.is_authenticated:
        try:
            db = get_db()
            username = current_user.name
            pomodoro = db.execute(
                "SELECT pomodoro_count FROM user WHERE name=?", (username,)
            ).fetchone()
            category = 'success'
            api_url = 'https://api.api-ninjas.com/v1/quotes?category={}'.format(
                category)
            response = requests.get(
                api_url, headers={'X-Api-Key': 'hpCwDT4pNvqjSB1N9K2Ngw==rvVHRFb9aIlm5LE9'})
            if response.status_code == requests.codes.ok:
                response = response.json()
                quote = response[0]['quote']
                author = response[0]['author']
                return render_template('homepage.html', quote=quote, author=author, username=current_user.name, pcount=pomodoro)
        except:
            return render_template('homepage.html', quote='Don’t wish it were easier. Wish you were better.', author='Jim Rohn', username=current_user.name)
    else:
        return render_template('index.html')


def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()


@app.route("/login")
def login():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)


@app.route("/login/callback")
def callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )
    client.parse_request_body_response(json.dumps(token_response.json()))
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)
    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        picture = userinfo_response.json()["picture"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400

    user = User(
        id_=unique_id, name=users_name, email=users_email, profile_pic=picture
    )
    if not User.get(unique_id):
        User.create(unique_id, users_name, users_email, picture)
    login_user(user)
    return redirect('/')


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/credits")
def credits():
    return render_template("credits.html")


@app.route('/unauthorized')
def unauthorized():
    return render_template('unauthorized.html')


@login_manager.unauthorized_handler
def unauthorized_callback():
    return redirect(url_for('unauthorized'))


@app.route('/resources')
@login_required
def resources():
    return render_template('resources.html', username=current_user.name)


@app.route('/timer')
@login_required
def timer():
    return render_template('timer.html', username=current_user.name)


@app.route('/pomodoro_finished', methods=['POST'])
def handle_pomodoro_finished():
    data = request.json
    username = data['username']
    db = get_db()
    row = db.execute(
        "SELECT pomodoro_count FROM users WHERE name=?", (username,)
    ).fetchone()
    count = row[0]
    count += 1
    db.execute(
        "UPDATE users SET pomodoro_count=? WHERE name=?", (count, username)
    )
    db.commit()
    return '', 204


@app.route('/meditation')
@login_required
def meditation():
    return render_template('meditation.html', ususername=current_user.name)


@app.route('/schedule')
@login_required
def schedule():
    service = get_calendar_service()
    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                          maxResults=10, singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])
    start = {}
    if not events:
        return render_template('schedule.html', events = ['No upcoming events found.'])
    return render_template('schedule.html', events=events)


if __name__ == "__main__":
    app.run(debug=True, ssl_context="adhoc")
