import os
import sys
import time
import requests
import secrets

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

def log_step(msg):
    print(f"\n[STEP] {msg}")

def log_success(msg):
    print(f"  ✅ {msg}")

def log_fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1) # Fail fast on critical issues

def do_request(session, method, url, max_retries=3, **kwargs):
    """
    Executes an HTTP request using the given session.
    Retries ONLY on network errors (ConnectionError, Timeout), NOT on logical HTTP errors (4xx, 5xx).
    """
    for attempt in range(max_retries):
        try:
            if method.lower() == 'get':
                resp = session.get(url, **kwargs)
            elif method.lower() == 'post':
                resp = session.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Return the response regardless of status code; 
            # let the test logic determine if 400/500 is a pass or fail.
            return resp
        
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                log_fail(f"Network error on {url} after {max_retries} attempts: {e}")
            print(f"    [Retry {attempt+1}/{max_retries}] Network error: {e}. Retrying...")
            time.sleep(1)

def main():
    test_id = secrets.token_hex(4)
    username = "kgarg8058"
    email = "kgarg8058@gmail.com"
    password = "LetmeDoit"
    waitlist_email = email
    
    # Two separate sessions to cleanly verify authentication flows
    auth_session = requests.Session()
    anon_session = requests.Session()

    print(f"=======================================================")
    print(f" Starting CodeAlive Black-Box E2E Tests")
    print(f" Target URL: {BASE_URL}")
    print(f" Test User:  {username}")
    print(f"=======================================================\n")

    # ---------------------------------------------------------
    # 1. Unauthenticated Checks & Negative Tests
    # ---------------------------------------------------------
    log_step("Negative Check: Unauthenticated access to /workspace redirects to /login")
    resp_ws = do_request(anon_session, 'get', f"{BASE_URL}/workspace", allow_redirects=False)
    if resp_ws.status_code in (302, 307) and "/login" in resp_ws.headers.get("Location", ""):
        log_success("Redirected to login correctly.")
    else:
        log_fail(f"/workspace did not redirect. Status: {resp_ws.status_code}, Location: {resp_ws.headers.get('Location')}")

    log_step("Negative Check: Unauthenticated access to /profile redirects to /login")
    resp_prof = do_request(anon_session, 'get', f"{BASE_URL}/profile", allow_redirects=False)
    if resp_prof.status_code in (302, 307) and "/login" in resp_prof.headers.get("Location", ""):
        log_success("Redirected to login correctly.")
    else:
        log_fail(f"/profile did not redirect. Status: {resp_prof.status_code}")

    log_step("Negative Check: Unauthenticated access to /api/workspace/created returns 401")
    resp_api_ws = do_request(anon_session, 'get', f"{BASE_URL}/api/workspace/created")
    if resp_api_ws.status_code == 401:
        log_success("API rejected unauthenticated access with 401.")
    else:
        log_fail(f"API returned {resp_api_ws.status_code} instead of 401.")

    log_step("Negative Check: Login with correct email but wrong password")
    bad_login_data = {"identifier": email, "password": "WrongPassword123!"}
    resp_bad_login = do_request(anon_session, 'post', f"{BASE_URL}/auth/login", json=bad_login_data)
    if resp_bad_login.status_code == 401:
        log_success("Invalid login properly rejected with 401.")
    else:
        log_fail(f"Invalid login returned {resp_bad_login.status_code} instead of 401.")

    # ---------------------------------------------------------
    # 2. Public Routes
    # ---------------------------------------------------------
    log_step("Testing Public Pages (Homepage and Waitlist)")
    resp_home = do_request(anon_session, 'get', f"{BASE_URL}/")
    if resp_home.status_code == 200:
        log_success("Homepage loaded successfully.")
    else:
        log_fail(f"Homepage failed with status {resp_home.status_code}")

    resp_waitlist = do_request(anon_session, 'get', f"{BASE_URL}/waitlist")
    if resp_waitlist.status_code == 200:
        log_success("Waitlist page loaded successfully.")
    else:
        log_fail(f"Waitlist page failed with status {resp_waitlist.status_code}")

    # ---------------------------------------------------------
    # 3. Waitlist Submission
    # ---------------------------------------------------------
    log_step(f"Testing Waitlist Submission")
    resp_wl_post = do_request(anon_session, 'post', f"{BASE_URL}/waitlist", data={"email": waitlist_email})
    if resp_wl_post.status_code == 200 and resp_wl_post.json().get("ok"):
        log_success("Waitlist API succeeded (inferring successful MongoDB insert).")
    elif resp_wl_post.status_code == 400 and "already added" in resp_wl_post.text:
        log_success("Waitlist API returned 400 (email already on waitlist, bypassing for this test).")
    else:
        log_fail(f"Waitlist submission failed: {resp_wl_post.status_code} - {resp_wl_post.text}")

    # ---------------------------------------------------------
    # 4. Auth Flow (Signup -> Login)
    # ---------------------------------------------------------
    log_step(f"Testing Signup Flow")
    signup_data = {"username": username, "email": email, "password": password}
    resp_signup = do_request(anon_session, 'post', f"{BASE_URL}/auth/signup", json=signup_data)
    if resp_signup.status_code == 200 and resp_signup.json().get("ok"):
        log_success("Signup API succeeded (inferring DB user creation).")
    elif resp_signup.status_code == 400 and ("already registered" in resp_signup.text or "already taken" in resp_signup.text):
        log_success("Signup API returned 400 (user already exists, continuing to login).")
    else:
        log_fail(f"Signup failed: {resp_signup.status_code} - {resp_signup.text}")

    log_step(f"Testing Login & Session Flow")
    login_data = {"identifier": email, "password": password}
    resp_login = do_request(auth_session, 'post', f"{BASE_URL}/auth/login", json=login_data)
    if resp_login.status_code == 200 and resp_login.json().get("ok"):
        log_success("Login API succeeded (verifying user exists).")
        # Validate Session Handling
        if "session_id" in auth_session.cookies:
            sess_id = auth_session.cookies.get('session_id')
            log_success(f"Session cookie successfully set: {sess_id[:10]}...")
            
            # CRITICAL FIX: The app sets Secure=True on the cookie.
            # Python's requests library respects this and WON'T send the cookie over http://localhost.
            # We must manually inject it into the session headers for local testing to work.
            auth_session.headers.update({"Cookie": f"session_id={sess_id}"})
        else:
            log_fail("Login succeeded but session_id cookie is missing in the response!")
    else:
        log_fail(f"Login failed: {resp_login.status_code} - {resp_login.text}")

    # ---------------------------------------------------------
    # 5. Authenticated Operations (Snippets & Workspace)
    # ---------------------------------------------------------
    log_step("Testing Authenticated Page Access")
    resp_ws_auth = do_request(auth_session, 'get', f"{BASE_URL}/workspace", allow_redirects=False)
    if resp_ws_auth.status_code == 200:
        log_success("/workspace page loaded successfully (no redirect).")
    else:
        log_fail(f"Authenticated /workspace returned {resp_ws_auth.status_code}")

    resp_prof_auth = do_request(auth_session, 'get', f"{BASE_URL}/profile", allow_redirects=False)
    if resp_prof_auth.status_code == 200:
        log_success("/profile page loaded successfully (no redirect).")
    else:
        log_fail(f"Authenticated /profile returned {resp_prof_auth.status_code}")

    log_step("Testing Authenticated Snippet Creation")
    snippet_title = f"E2E Title {test_id}"
    snippet_data = {
        "code": "print('Black-box E2E Test')",
        "language": "python",
        "highlights": "L1",
        "title": snippet_title,
        "password": "secret_snippet",
        "expiry": 30
    }
    resp_save = do_request(auth_session, 'post', f"{BASE_URL}/save", data=snippet_data)
    
    if resp_save.status_code == 200 and "url" in resp_save.json():
        snippet_url = resp_save.json()["url"]
        log_success(f"Snippet creation API succeeded. Return URL: {snippet_url}")
    else:
        log_fail(f"Snippet creation failed: {resp_save.status_code} - {resp_save.text}")

    log_step("Verifying Snippet Database Update via API")
    resp_ws_api = do_request(auth_session, 'get', f"{BASE_URL}/api/workspace/created")
    if resp_ws_api.status_code == 200:
        snippets = resp_ws_api.json().get("snippets", [])
        found = any(s.get("title") == snippet_title for s in snippets)
        if found:
            log_success(f"Snippet '{snippet_title}' found via /api/workspace/created.")
            log_success("✅ DB inferred strictly: Snippet insertion was successful.")
        else:
            log_fail("Snippet creation succeeded via /save, but it's missing from /api/workspace/created list.")
    else:
        log_fail(f"Failed to fetch workspace API: {resp_ws_api.status_code}")

    log_step("Testing Language Detection API")
    resp_detect = do_request(anon_session, 'post', f"{BASE_URL}/detect-language", json={"code": "def hello_world():\n    print('test')"})
    if resp_detect.status_code == 200 and resp_detect.json().get("language") == "python":
        log_success("Language detection API successfully identified Python.")
    else:
        log_fail(f"Language detection failed: {resp_detect.status_code} - {resp_detect.text}")

    log_step("Testing Shared Snippet Access & Password Protection")
    # Fetch snippet anonymously
    resp_shared = do_request(anon_session, 'get', f"{BASE_URL}{snippet_url}")
    if resp_shared.status_code == 200:
        log_success("Shared snippet URL loaded successfully.")
    else:
        log_fail(f"Shared snippet URL failed: {resp_shared.status_code}")

    code_id = snippet_url.split('/')[-1]

    log_step("Negative Check: Verify Snippet with Wrong Password")
    resp_verify_bad = do_request(auth_session, 'post', f"{BASE_URL}/api/snippets/{code_id}/verify", json={"password": "wrongpassword"})
    if resp_verify_bad.status_code == 401:
        log_success("Wrong snippet password properly rejected with 401.")
    else:
        log_fail(f"Wrong snippet password returned {resp_verify_bad.status_code} instead of 401.")

    log_step("Testing Snippet Password Verification (Positive)")
    # Must use auth_session or anon_session. We'll use auth_session to test owner accessing it or anon_session.
    # We use anon_session to prove anyone with a password can unlock it.
    # Note: wait, verify endpoint requires login!
    # Let's check api_snippets.py for verify endpoint.
    # "user_id = getattr(request.state, 'user_id', None); if not user_id: raise HTTPException(401, 'Login required')"
    # Ah! The verify endpoint requires login to track access control. 
    # Let's use auth_session so it succeeds.
    resp_verify_ok = do_request(auth_session, 'post', f"{BASE_URL}/api/snippets/{code_id}/verify", json={"password": "secret_snippet"})
    if resp_verify_ok.status_code == 200 and resp_verify_ok.json().get("ok"):
        log_success("Correct snippet password accepted successfully.")
    else:
        log_fail(f"Correct snippet password rejected: {resp_verify_ok.status_code} - {resp_verify_ok.text}")

    print(f"\n=======================================================")
    print(f" 🎉 All Black-Box E2E Tests Passed Successfully! ")
    print(f"=======================================================\n")

if __name__ == "__main__":
    main()
