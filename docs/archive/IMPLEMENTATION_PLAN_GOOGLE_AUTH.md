# Implementation Plan: Google Authentication for AI Market Abuse Detection Arena

> **Historical record — reviewed 2026-09-21.** Implementation paths, endpoints,
> resource values and completion claims below belong to the recorded revision.
> They are not current deployment instructions. Google Auth was removed; secure
> workspace restoration remains #91. Use the [current roadmap](../roadmap/CURRENT_STATUS.md)
> and [deployment guide](../deployment/nebius-deployment.md) for active scope.

## Overview

This document outlines the plan to re-implement Google OAuth authentication for the LOB Arena project. The authentication was previously implemented in commits `4af2ebe` through `22ffa3a` and `d27b52b`, but was removed in commit `68fb0c3` as part of archiving unused modules for the competition submission. This plan restores the authentication for the authorized user scenario requirements.

**Goal**: Enable Google OAuth login so that detection scenario runs can be linked to the exact logged-in user, with results saved and associated with their identity.

---

## Architecture Context

### Current Stack
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS
- **Backend**: FastAPI (Python 3.14) with local JSONL storage
- **Authentication**: Previously used Google Identity Services (GIS) with OAuth 2.0 Authorization Code flow via popup

### Key Architecture Decisions (from ARD-0012)
1. **Stable Google user identity** via `google_id = payload.sub` (SHA-256 of subject/email)
2. **App-issued HS256 JWT** after Google verification - Google tokens NOT used as long-lived app sessions
3. **Backward-compatible session header** `X-NMAA-Session-ID` + `Authorization: Bearer <app-jwt>`
4. **Frontend maps authenticated users** into platform identity model (ARD-0014); falls back to "Demo Analyst" / "Aimada Surveillance Desk" when Google not configured
5. **Local demo mode works** without Google credentials

---

## Implementation Plan

### Phase 1: Backend Authentication Infrastructure

#### 1.1 Backend Auth Module Structure
Create `backend/app/auth/` directory with:
```
backend/app/auth/
├── __init__.py
├── persona.py        # User/session management, Google identity mapping
├── jwt.py            # HS256 JWT issuance and validation
├── store.py          # Local JSONL storage for auth data
└── routes.py         # FastAPI auth endpoints (or in api/routes_auth.py)
```

#### 1.2 Persona Management (`persona.py`)
**Key functions to implement:**
- `user_id_for_google_identity(subject: str | None, email: str | None) -> str` - Creates stable user ID from Google subject/email
- `create_session(store, email, name, role, google_subject, avatar_url) -> dict` - Creates user + session records
- `find_session(store, session_id) -> dict | None` - Finds active session by ID
- `update_role(store, session_id, role) -> dict | None` - Updates user role (attacker/defender/observer/judge)
- `save_session_history(store, session_id, window_hours=24) -> dict | None` - Persists simulation history for session restore
- `close_session(store, session_id) -> dict | None` - Logout with history preservation
- `_user_history_path(user_id) -> str` - Safe filesystem path for user history

**Data structures:**
- `ArenaRole = Literal["attacker", "defender", "observer", "judge"]`
- `AuthUser` - user_id, provider, google_subject, email, name, avatar_url, created_at
- `AuthSession` - session_id, user_id, role, created_at, last_seen_at, active

#### 1.3 JWT Handling (`jwt.py`)
- `SECRET_KEY` from settings (HS256)
- `create_access_token(user_id, role, expires_in_hours=24) -> str`
- `decode_access_token(token) -> dict | None`
- `SESSION_HEADER = "X-NMAA-Session-ID"`

#### 1.4 Local Storage (`store.py`)
- JSONL append/read for `auth/users.jsonl`, `auth/sessions.jsonl`
- Session history artifacts under `auth/users/{safe_user_id}/`

#### 1.5 Auth API Routes (`backend/app/api/routes_auth.py`)
**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/google/config` | Returns `{configured: bool, client_id: str}` |
| POST | `/api/auth/google/login` | Completes Google login with auth code |
| POST | `/api/auth/session` | Creates/refreshes demo session |
| GET | `/api/auth/session/{session_id}` | Gets current session |
| POST | `/api/auth/session/{session_id}/role` | Updates role |
| POST | `/api/auth/session/{session_id}/save` | Saves simulation history |
| POST | `/api/auth/session/{session_id}/close` | Logout |
| GET | `/api/auth/personas` | Lists available roles |

**Request/Response models** (Pydantic):
- `GoogleLoginRequest`: `authorization_code`, `redirect_uri`, `role`
- `GoogleLoginResponse`: `user`, `session`, `access_token`, `restored_history`
- `SessionResponse`: `user`, `session`
- `RoleUpdateRequest`: `role`, `access_token`

#### 1.6 Settings Integration (`backend/app/config.py`)
Add to `Settings` class:
```python
google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
google_redirect_uri: str = Field(default="http://localhost:5173/auth/callback", alias="GOOGLE_REDIRECT_URI")
auth_jwt_secret: str = Field(default_factory=lambda: secrets.token_hex(32), alias="AUTH_JWT_SECRET")
auth_session_ttl_hours: float = Field(default=24.0, ge=0.5, le=168.0, alias="AUTH_SESSION_TTL_HOURS")
```

---

### Phase 2: Frontend Authentication Context

#### 2.1 Auth State Types (`frontend/src/auth/authState.ts`)
```typescript
export type ArenaRole = "attacker" | "defender" | "observer" | "judge";

export interface AuthUser {
  user_id: string;
  provider: "google" | "demo";
  google_subject?: string;
  email: string;
  name: string;
  avatar_url?: string;
  created_at: string;
}

export interface AuthSession {
  session_id: string;
  user_id: string;
  role: ArenaRole;
  created_at: string;
  last_seen_at: string;
  active: boolean;
}

export interface AuthState {
  busy: boolean;
  error: string | null;
  lastMessage: string | null;
  role: ArenaRole;
  session: AuthSession | null;
  user: AuthUser | null;
  platformUser: PlatformUser | null;
  workspace: WorkspaceConfig | null;
  loginWithGoogle: (nextRole?: ArenaRole) => Promise<void>;
  setRole: (role: ArenaRole) => Promise<void>;
  saveNow: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}
```

#### 2.2 Auth Context (`frontend/src/auth/AuthContext.tsx`)
**Provider responsibilities:**
- Session persistence in `localStorage` (key: `aimada.auth.session`)
- Auto-restore session on app load
- `beforeunload` handler to save history
- Google OAuth flow via GIS popup
- Role selection and session management

**Key functions:**
- `loadGoogleIdentityServices()` - Loads `https://accounts.google.com/gsi/client`
- `requestGoogleAuthorizationCode(clientId, redirectUri)` - Opens Google popup, returns auth code
- `applyAuthResponse(response, fallbackMessage)` - Applies backend auth response to state
- `loginWithGoogle(nextRole)` - Orchestrates Google OAuth or demo fallback

#### 2.3 Auth Hook (`frontend/src/auth/useAuth.ts`)
```typescript
export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
```

#### 2.4 Platform Identity (`frontend/src/platform/identity.ts`)
Maps `AuthUser` + `ArenaRole` to `PlatformUser` and `WorkspaceConfig`:
- `platformUserFromAuth(user, role)` - Creates platform identity
- `workspaceForUser(platformUser)` - Returns workspace config (role-based UI)

---

### Phase 3: Frontend Integration

#### 3.1 App Wrapper (`frontend/src/App.tsx`)
Wrap entire app with `AuthProvider`:
```tsx
<AuthProvider>
  <BrowserRouter>
    {/* existing routes */}
  </BrowserRouter>
</AuthProvider>
```

#### 3.2 Login UI Components
- **Login Curtain** (OpenAI-style): Full-screen overlay with Google sign-in button
- **Role Selector**: Attacker / Defender / Observer / Judge buttons
- **User Avatar/Name** in topbar when logged in
- **Logout** button in user menu

#### 3.3 API Client (`frontend/src/api/client.ts`)
Add auth endpoints:
```typescript
export async function getGoogleAuthConfig(): Promise<{configured: boolean; client_id: string}>;
export async function completeGoogleLogin(role: ArenaRole, data: {authorization_code: string; redirect_uri: string}): Promise<AuthResponse>;
export async function getCurrentAuthSession(sessionId: string, accessToken?: string): Promise<AuthResponse>;
export async function updateAuthRole(sessionId: string, role: ArenaRole, accessToken: string): Promise<AuthResponse>;
export async function saveAuthSession(sessionId: string, onUnload: boolean, accessToken?: string): Promise<SaveResponse>;
export async function logoutAuthSession(sessionId: string, accessToken?: string): Promise<void>;
```

---

### Phase 4: Configuration & Environment

#### 4.1 Environment Variables (`.env.example`)
```bash
# Google OAuth (optional - demo mode works without)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:5173/auth/callback

# Auth JWT
AUTH_JWT_SECRET=
AUTH_SESSION_TTL_HOURS=24.0
```

#### 4.2 Frontend Runtime Config (`frontend/runtime-config.js.template`)
```javascript
window.__RUNTIME_CONFIG__ = {
  googleClientId: "{%GOOGLE_CLIENT_ID%}",
  authRedirectUri: "{%GOOGLE_REDIRECT_URI%}",
  // ... existing config
};
```

#### 4.3 Docker Compose Updates
- Pass `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` to frontend/backend services
- Ensure frontend redirect URI matches deployed origin

---

### Phase 5: Testing & Validation

#### 5.1 Local Demo Mode (No Google Config)
- App starts in "Demo Analyst" mode
- Role selector works (attacker/defender/observer/judge)
- Session persists in localStorage
- History save/restore works
- No Google OAuth attempt

#### 5.2 Google OAuth Flow (With Credentials)
1. Configure Google Cloud Console:
   - OAuth 2.0 Client ID (Web application)
   - Authorized JavaScript origins: `http://localhost:5173`, `https://your-domain.com`
   - Authorized redirect URIs: `http://localhost:5173/auth/callback`
2. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` in `.env`
3. Start stack: `docker compose --env-file .env up --build`
4. Open `http://localhost:5173` → Login curtain appears
5. Click "Continue with Google" → Popup opens → Consent → Returns to app
6. Backend exchanges code for tokens, creates session, returns JWT
7. User sees role selector, picks role, enters arena

#### 5.3 Detection Scenario Linkage
- When user runs detection scenario (spoofing, layering, etc.)
- Backend tags incident/simulation artifacts with `session_id` and `user_id`
- Results saved under `auth/users/{user_id}/history/`
- Evidence archive includes `restored_for_session_id` linkage

#### 5.4 Test Checklist
| Test | Local Demo | Google OAuth |
|------|------------|--------------|
| App loads without auth config | ✅ | ✅ |
| Role selector visible | ✅ | ✅ |
| Session persists across reload | ✅ | ✅ |
| History save/restore | ✅ | ✅ |
| Google popup opens | N/A | ✅ |
| Code exchange works | N/A | ✅ |
| Backend creates user/session | N/A | ✅ |
| JWT issued and validated | N/A | ✅ |
| Incident tagged with user_id | ✅ | ✅ |
| Evidence archive restorable | ✅ | ✅ |

---

### Phase 6: Deployment & PR Workflow

#### 6.1 Isolated Feature Branch
```bash
git checkout -b feature/google-auth-restoration
# Implement all changes
git add -A
git commit -m "feat(auth): restore Google OAuth authentication with persona system"
```

#### 6.2 Local Deployment Test
```bash
# 1. Copy environment
cp .env.example .env
# 2. Add Google credentials to .env
# 3. Build and start
docker compose --env-file .env up --build
# 4. Test at http://localhost:5173
```

#### 6.3 Online Login Test
1. Configure Google Cloud OAuth credentials
2. Update `.env` with real `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
3. Restart stack
4. Complete full login flow
5. Run detection scenario
6. Verify artifacts linked to user in `outputs/auth/users/...`

#### 6.4 Results Saving
- Save test evidence to `evidence/auth-test-<date>/`
- Include: login flow screenshots, incident cards with user tags, restored history verification
- Document any issues in `evidence/auth-test-<date>/notes.md`

#### 6.5 PR Submission
```bash
git push origin feature/google-auth-restoration
# Create PR via GitHub CLI
gh pr create --title "feat(auth): restore Google OAuth authentication" \
  --body-file docs/archive/IMPLEMENTATION_PLAN_GOOGLE_AUTH.md
```

---

## File Creation Summary

### New Backend Files
| File | Purpose |
|------|---------|
| `backend/app/auth/__init__.py` | Auth module exports |
| `backend/app/auth/persona.py` | User/session management |
| `backend/app/auth/jwt.py` | JWT creation/validation |
| `backend/app/auth/store.py` | LocalStore JSONL helpers |
| `backend/app/api/routes_auth.py` | FastAPI auth endpoints |
| `backend/tests/test_auth_persona.py` | Unit tests for persona logic |

### Modified Backend Files
| File | Changes |
|------|---------|
| `backend/app/config.py` | Add Google OAuth + JWT settings |
| `backend/app/main.py` | Include auth router |
| `backend/app/storage/local_store.py` | Ensure JSONL append/read supports auth paths |
| `backend/pyproject.toml` | Add any new dependencies (pyjwt, etc.) |

### New Frontend Files
| File | Purpose |
|------|---------|
| `frontend/src/auth/authState.ts` | Auth state types |
| `frontend/src/auth/AuthContext.tsx` | Auth provider + Google OAuth logic |
| `frontend/src/auth/useAuth.ts` | React hook for auth context |
| `frontend/src/platform/identity.ts` | Platform user/workspace mapping |

### Modified Frontend Files
| File | Changes |
|------|---------|
| `frontend/src/App.tsx` | Wrap with AuthProvider |
| `frontend/src/api/client.ts` | Add auth API functions |
| `frontend/src/components/` | Add login curtain, role selector, user avatar |
| `frontend/runtime-config.js.template` | Add Google client ID config |
| `frontend/Dockerfile` | Pass runtime config |

### Configuration Files
| File | Changes |
|------|---------|
| `.env.example` | Add Google OAuth + JWT vars |
| `docker-compose.yml` | Pass auth env vars to services |
| `deployments/modes/local-demo.env` | Demo mode defaults |

---

## Rollback Plan

If issues arise:
1. Revert to commit before feature branch: `git checkout main`
2. The app works in demo mode without auth (fallback is built-in)
3. No database migrations needed (local JSONL only)

---

## References

- **Original Implementation Commits**: `4af2ebe`, `b34a9e9`, `22ffa3a`, `d27b52b`
- **Architecture Doc**: `docs/architecture/ARD-0012-google-authentication.md` (to be recreated)
- **Platform Identity Doc**: `docs/architecture/ARD-0014-multiuser-platform-foundation.md` (to be recreated)
- **Google Identity Services**: https://developers.google.com/identity/gsi/web/guides/overview
- **OAuth 2.0 Authorization Code Flow**: https://datatracker.ietf.org/doc/html/rfc6749

---

## Next Steps

1. **Immediate**: Create backend auth module files (Phase 1)
2. **Day 1-2**: Implement frontend auth context and UI (Phase 2-3)
3. **Day 3**: Configuration and local testing (Phase 4-5)
4. **Day 4**: Google Cloud OAuth setup and online testing (Phase 5)
5. **Day 5**: Evidence collection and PR submission (Phase 6)