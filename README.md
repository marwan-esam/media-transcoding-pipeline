# HLS Media Transcoding Pipeline

An asynchronous, highly scalable video processing architecture. This system allows users to securely upload raw video files, which are queued and processed by background workers into Adaptive Bitrate HLS streams (1080p, 720p, 480p) using FFmpeg, and delivered back to the client with real-time WebSocket progress updates.

## Architecture Stack
* **Framework:** FastAPI (Python 3.11)
* **Process Management:** Uvicorn (4 Async Workers)
* **Database:** PostgreSQL 16 (Async SQLAlchemy & Alembic)
* **Object Storage:** MinIO (S3-Compatible, separated into raw and processed buckets)
* **Message Broker:** RabbitMQ 3 (Durable queues with Dead Letter Exchanges for failed jobs)
* **Real-Time Engine:** WebSockets & Redis 7 Pub/Sub
* **Security:** JWT HttpOnly Cookies, Argon2 Password Hashing, slowapi Rate Limiting, File Size Middleware (500MB max)
* **Infrastructure:** Docker & Docker Compose
* **Production Deployment:** Oracle Cloud (Ubuntu), Caddy Reverse Proxy, Let's Encrypt SSL/TLS

---

## Live Production Endpoints
The application is actively deployed and secured via SSL/TLS.
* **REST API & Swagger UI:** [https://transcoder-marwan.developer.li/docs](https://transcoder-marwan.developer.li/docs)
* **WebSocket Engine:** `wss://transcoder-marwan.developer.li/videos/{video_id}/ws`
* **Video Asset Storage (MinIO):** `https://transcoder-marwan.developer.li/processed-videos/`

---

## Running the Project Locally

The environment is fully containerized. Docker is the only local requirement.

### 1. Boot the Production Stack
Spins up PostgreSQL, MinIO, RabbitMQ, Redis, the FastAPI backend, the FFmpeg worker, and Caddy.
```bash
docker compose up --build -d
```

### 2. Run the Isolated Test Suite
Executes the comprehensive `pytest` suite within a dedicated test environment, isolating databases and message brokers to prevent data contamination.
```bash
docker compose -f docker-compose.test.yml up --build
```

---

## REST API Documentation

### Authentication (`/auth`)
* **`POST /auth/register`**
  * **Rate Limit:** 3 per minute
  * **Payload:** `{"email": "user@example.com", "password": "securepassword"}`
  * **Returns:** `201 Created` | `{"message": "User created successfully"}`
* **`POST /auth/login`**
  * **Rate Limit:** 5 per minute
  * **Payload:** `{"email": "user@example.com", "password": "securepassword"}`
  * **Returns:** `200 OK` | Sets an `HttpOnly`, `Lax` JWT `access_token` cookie for session management.
* **`POST /auth/logout`**
  * **Returns:** `200 OK` | Deletes the `access_token` cookie.
* **`GET /auth/ticket`** *(Requires Auth)*
  * **Description:** Generates a short-lived (15s) Redis ticket used to securely authenticate WebSocket connections.
  * **Returns:** `200 OK` | `{"ticket": "uuid-string"}`
* **`GET /auth/users/me`** *(Requires Auth)*
  * **Returns:** `200 OK` | `{"id": "uuid", "email": "user@example.com", "is_active": true, ...}`

### Videos (`/videos`)
* **`POST /videos/upload`** *(Requires Auth)*
  * **Rate Limit:** 2 per minute (Max 500MB payload)
  * **Format:** `multipart/form-data` 
  * **Payload:** `file` (.mp4, .mkv, .avi), `title` (optional, min 3 chars)
  * **Returns:** `201 Created` | Returns the `VideoResponse` object with `status: "queued"`.
* **`GET /videos`** *(Requires Auth)*
  * **Returns:** `200 OK` | Array of `VideoResponse` objects belonging to the current user, ordered by newest first.
* **`GET /videos/{video_id}`** *(Requires Auth)*
  * **Returns:** `200 OK` | `VideoResponse` object containing dynamic `stream_url` and `thumbnail_url` (if status is "completed").
* **`DELETE /videos/{video_id}`** *(Requires Auth)*
  * **Description:** Deletes the database record and triggers a background task to wipe all associated S3 chunks and playlists from MinIO.
  * **Returns:** `204 No Content`

---

## Real-Time WebSocket Protocol

Because standard browsers do not send HTTP cookies during WebSocket handshakes, this system utilizes a secure Ticketing pattern.

### 1. Obtain a Ticket
The client must first call `GET /auth/ticket` via standard HTTP to receive a 15-second, single-use ticket stored in Redis.

### 2. Establish Connection
The client connects to the WebSocket endpoint, appending the ticket as a query parameter.
**Endpoint:** `wss://transcoder-marwan.developer.li/videos/{video_id}/ws?ticket=<your_ticket_here>`

*If the ticket is missing, invalid, or expired, the server will close the connection with `WS_1008_POLICY_VIOLATION`.*

### 3. Real-Time Event Payloads
Once authenticated, the server verifies the user's ownership of the requested video and streams FFmpeg processing progress directly from the Redis Pub/Sub channel.

**Server -> Client (Connection Established):**
```json
{
  "video_id": "uuid",
  "status": "queued",
  "message": "Listening for real-time updates..."
}
```

**Server -> Client (FFmpeg Progress Updates):**
```json
{
  "video_id": "uuid",
  "status": "45%"
}
```

**Server -> Client (Completion / Termination):**
```json
{
  "video_id": "uuid",
  "status": "completed" 
}
```
*(The socket safely closes with `WS_1000_NORMAL_CLOSURE` upon successful completion or failure).*