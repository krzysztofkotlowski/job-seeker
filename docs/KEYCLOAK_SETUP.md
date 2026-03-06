# Keycloak Setup for Job Seeker

## Pre-configured (Docker Compose)

When using `docker compose up`, the **jobseeker** realm and **jobseeker-frontend** client are imported automatically from `keycloak/import/jobseeker-realm.json`. No manual setup needed.

You still need to create a user to log in:

1. Access **http://localhost:8080** (admin console)
2. Log in with `admin` / `admin`
3. Select realm **jobseeker** (top-left dropdown)
4. Go to **Users** → **Add user**
5. Username: `demo`, Email: `demo@example.com`
6. Open **Credentials** tab → Set password

## Manual Setup (if not using the import)

If the realm import fails or you run Keycloak separately:

### 1. Create Realm

1. Log in with `admin` / `admin`
2. Hover over "master" (top-left) and click "Create realm"
3. Name: `jobseeker`
4. Click "Create"

### 2. Create Client

1. Go to **Clients** → **Create client**
2. **Client ID:** `jobseeker-frontend`
3. **Client authentication:** OFF (public client)
4. **Root URL:** `http://localhost:5173`
5. **Valid redirect URIs:** `http://localhost:5173/*`
6. **Valid post logout redirect URIs:** `http://localhost:5173/*`
7. **Web origins:** `http://localhost:5173`
8. Click "Save"

### 3. Realm SSL (if you see "HTTPS required")

Realm settings → Security defenses → Headers → **SSL required:** None

## Environment

- **Backend:** `KEYCLOAK_URL` (internal, e.g. `http://keycloak:8080`), `KEYCLOAK_PUBLIC_URL` (browser, e.g. `http://localhost:8080`), `KEYCLOAK_REALM`
- **Frontend:** Gets config from `/api/v1/auth/config` (no env vars needed)
