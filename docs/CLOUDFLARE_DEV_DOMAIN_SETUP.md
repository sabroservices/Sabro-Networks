# Sabro Networks — Cloudflare Python Workers, Neon PostgreSQL & `.dev` Custom Domain Architecture Guide

This guide details the complete deployment, network routing, edge SSL/TLS, and zero-maintenance architecture for operating **Sabro Networks** on **Cloudflare Python Workers**, **Neon PostgreSQL**, **Cloudflare Hyperdrive**, and **Cloudflare R2** under a custom **`.dev`** domain on a **$0 infrastructure budget**.

---

## 1. System Architecture Overview

```
                      ┌─────────────────────────────────────────┐
                      │        Browser / Operator / NOC         │
                      └────────────────────┬────────────────────┘
                                           │ HTTPS (TLS 1.3 / HSTS)
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │      Cloudflare Edge CDN & Anycast      │
                      │  - Custom .dev Domain (portal.xxx.dev)  │
                      │  - Free-Tier WAF & Rate Limiting        │
                      │  - Full (Strict) SSL & DDoS Protection  │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │      Cloudflare Python Worker           │
                      │  - Python 3.12 (Pyodide WebAssembly)    │
                      │  - Flask WSGI Edge Bridge (workers.wsgi)│
                      │  - Pure-Python pg8000 DB-API Driver     │
                      └─────────────┬─────────────────────┬─────┘
                                    │                     │
                    Hyperdrive / SQL│                     │S3 API
                                    ▼                     ▼
              ┌───────────────────────────┐  ┌───────────────────────────┐
              │   Cloudflare Hyperdrive   │  │       Cloudflare R2       │
              │  - Connection pooling     │  │  - Zero egress cost       │
              │  - Low-latency TCP proxy  │  │  - Avatars & docs storage │
              └─────────────┬─────────────┘  │  - Encrypted DB backups   │
                            │                └───────────────────────────┘
                            ▼
              ┌───────────────────────────┐
              │      Neon PostgreSQL      │
              │  - Serverless PostgreSQL  │
              │  - 0.5 GB Free Tier       │
              │  - Auto-suspend & resume  │
              └───────────────────────────┘
```

---

## 2. Prerequisites & Environment Setup

1. **Cloudflare Account**: Free tier (includes unlimited Worker requests under 100k/day, unlimited R2 storage under 10GB free, free SSL/TLS, free DNS).
2. **Neon Account**: Free serverless PostgreSQL instance (creates standard connection URI).
3. **Domain**: Any custom `.dev` domain registered via Google Domains / Cloudflare Registrar / Porkbun (note: `.dev` TLD is on the HSTS preload list and requires HTTPS by default).

---

## 3. Step-by-Step Deployment Instructions

### Step 3.1: Database Provisioning (Neon PostgreSQL)
1. Sign in to [Neon Console](https://console.neon.tech).
2. Create project `sabro-networks`.
3. Copy your PostgreSQL connection string:
   ```text
   postgresql://user:password@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
4. Run the schema migrations in the Neon SQL Editor:
   - Execute `migrations/001_initial_schema.sql` (Creates all 20 relational tables, foreign keys, and performance indexes).
   - Execute `migrations/002_seed_packages.sql` (Pre-seeds standard tariff plans: Sparko, Veloza, Nexora, Zentro, Voltra, Astrix, Maxora).

### Step 3.2: Cloudflare Hyperdrive Setup
Hyperdrive accelerates PostgreSQL queries by keeping warm pooled TCP connections close to your Neon database:
1. In Cloudflare Dashboard, navigate to **Storage & Databases** > **Hyperdrive** > **Create Config**.
2. Fill in database parameters:
   - **Name**: `sabro-hyperdrive`
   - **Host**: `ep-xxxx.ap-southeast-1.aws.neon.tech`
   - **Port**: `5432`
   - **Database**: `neondb`
   - **Username**: `[your-neon-user]`
   - **Password**: `[your-neon-password]`
3. Note the generated **Hyperdrive ID** (e.g. `9f3c...`) and update `cloudflare/wrangler.jsonc`.

### Step 3.3: Cloudflare R2 Storage Bucket
1. Navigate to **R2 Object Storage** > **Create Bucket**.
2. **Bucket Name**: `sabro-networks-storage`.
3. Under **Settings** > **R2 API Tokens**, create a token with `Admin Read & Write` permissions.
4. Note `Account ID`, `Access Key ID`, and `Secret Access Key`.

### Step 3.4: Worker Deployment with Wrangler
1. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```
2. Authenticate to Cloudflare:
   ```bash
   wrangler login
   ```
3. Set production secrets:
   ```bash
   wrangler secret put DATABASE_URL
   # Paste your Neon PostgreSQL connection string

   wrangler secret put CLOUDFLARE_R2_ACCESS_KEY_ID
   wrangler secret put CLOUDFLARE_R2_SECRET_ACCESS_KEY
   wrangler secret put CLOUDFLARE_R2_ACCOUNT_ID
   ```
4. Deploy the Worker:
   ```bash
   wrangler deploy --config cloudflare/wrangler.jsonc
   ```

---

## 4. Custom `.dev` Domain & DNS Configuration

1. In Cloudflare Dashboard, go to **Workers & Pages** > **sabro-networks** > **Settings** > **Domains & Routes**.
2. Click **Add** > **Custom Domain**.
3. Enter your domain: `portal.sabronetworks.dev` (or apex `sabronetworks.dev`).
4. Cloudflare automatically:
   - Adds an orange-cloud Proxied DNS CNAME record pointing to your worker.
   - Issues a universal SSL/TLS edge certificate within 60 seconds.

### SSL/TLS Edge Settings
1. Navigate to **SSL/TLS** > **Overview**: Set to **Full (Strict)**.
2. Navigate to **SSL/TLS** > **Edge Certificates**:
   - **Always Use HTTPS**: `ON`
   - **HTTP Strict Transport Security (HSTS)**:
     - Status: `Enabled`
     - Max-Age: `12 months (31536000 seconds)`
     - Include subdomains: `ON`
     - Preload: `ON`
   - **Minimum TLS Version**: `TLS 1.2`
   - **Opportunistic Encryption**: `ON`
   - **TLS 1.3**: `ON`

---

## 5. Free-Tier Security Hardening & Rate Limiting

To safeguard customer data and prevent brute-force attacks at $0 cost:
1. Navigate to **Security** > **WAF** > **Rate Limiting Rules** > **Create Rule**:
   - **Rule Name**: `Protect Login Endpoint`
   - **Expression**: `(http.request.uri.path eq "/login" and http.request.method eq "POST")`
   - **Requests**: `10 requests per 1 minute`
   - **Action**: `Block` (or `Managed Challenge`) for `10 minutes`
2. Navigate to **Security** > **Bots**:
   - Enable **Bot Fight Mode** to mitigate automated scrapers.

---

## 6. Automated Backup & Recovery Verification

Automated backups run every day at 02:00 UTC via GitHub Actions (`.github/workflows/backup.yml`):
1. **Dumping**: Extracts database records using transactional queries.
2. **Compression**: Gzip-compressed.
3. **Archival**: Uploaded to `sabro-networks-storage/backups/`.
4. **Disaster Recovery**: To restore a snapshot, navigate to `/backup/db` in the Sabro Networks portal and upload the `.sql.gz` or `.db` snapshot, or run `psql "$DATABASE_URL" < backup.sql`.
