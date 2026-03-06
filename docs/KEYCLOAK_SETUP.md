# Keycloak Setup for Job Seeker

## Optional Authentication

**Auth is optional.** The app works without Keycloak. Users can browse jobs, run resume analysis, and use most features without logging in. Login is only required when you want to:

- Save resume analyses to your account
- Use protected endpoints (import, backup)

### Enabling Keycloak (Docker Compose)

By default, Keycloak is **disabled**. To enable auth:

1. Start Keycloak with the `keycloak` profile:
   ```bash
   docker compose --profile keycloak up --build
   ```

2. Set `KEYCLOAK_ENABLED=true` for the backend. Create a `.env` file in the project root:
   ```
   KEYCLOAK_ENABLED=true
   ```
   Then run: `docker compose --profile keycloak up --build`

   Or pass it inline: `KEYCLOAK_ENABLED=true docker compose --profile keycloak up`

3. Import the realm (see below) and create a user.

## Pre-configured (Docker Compose)

When using Keycloak, the **jobseeker** realm and **jobseeker-frontend** client can be imported from `keycloak/import/jobseeker-realm.json`. Configure Keycloak to import this on startup if needed.

Create a user to log in:

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

- **Backend:** `KEYCLOAK_URL` (internal, e.g. `http://keycloak:8080`), `KEYCLOAK_PUBLIC_URL` (browser, e.g. `http://localhost:8080`), `KEYCLOAK_REALM`, `KEYCLOAK_ENABLED` (must be `true` to enable auth; default `false`)
- **Frontend:** Gets config from `/api/v1/auth/config` (no env vars needed)
