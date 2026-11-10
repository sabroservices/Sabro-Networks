# Complete Guide: Deploying Sabro Networks on Oracle Cloud (100% Free Forever) with a Free Domain & Free SSL

---

### Table of Contents
1. [Overview & Free Resources](#1-overview--free-resources)
2. [Step 1: Get a 100% Free Domain (DuckDNS or Cloudflare)](#step-1-get-a-100-free-domain-duckdns)
3. [Step 2: Create Your Free Oracle Cloud Virtual Machine](#step-2-create-your-free-oracle-cloud-virtual-machine)
4. [Step 3: Open Firewall Ports (Port 80 & 443)](#step-3-open-firewall-ports-port-80--443)
5. [Step 4: Upload Sabro Networks to Your Oracle VM](#step-4-upload-sabro-networks-to-your-oracle-vm)
6. [Step 5: Run 1-Click Automated Setup (`deploy_oracle.sh`)](#step-5-run-1-click-automated-setup-deploy_oraclesh)
7. [Step 6: Activate Free Let's Encrypt SSL (HTTPS)](#step-6-activate-free-lets-encrypt-ssl-https)
8. [Production Maintenance & Daily Operations](#production-maintenance--daily-operations)

---

### 1. Overview & Free Resources

You can host **Sabro Networks Powered By Connect (FTTH)** on the internet 24/7/365 with **Zero Cost (\$0/month)**:

| Component | Provider | Cost | Specs |
|:---|:---|:---:|:---|
| **Cloud Hosting** | Oracle Cloud Always Free | **\$0.00 / Free Forever** | 1–4 OCPU, up to 24 GB RAM, 200 GB Storage, Free Public IP |
| **Domain Name** | DuckDNS or Cloudflare | **\$0.00 / Free Forever** | `sabronetworks.duckdns.org` (or custom domain) |
| **SSL Certificate** | Let's Encrypt (Certbot) | **\$0.00 / Free Forever** | Green Padlock `https://` with auto-renewal |
| **Web Server** | Nginx + Gunicorn | **Open Source** | High concurrency for multi-user field access |

---

### Step 1: Get a 100% Free Domain (DuckDNS)

1. Go to **[https://www.duckdns.org](https://www.duckdns.org)**.
2. Sign in with Google, GitHub, or Reddit (instant, no credit card required).
3. Under **domains**, choose your subdomain name, e.g.:
   - Type: `sabronetworks`
   - Click **Add Domain**
4. Your free domain is now: **`sabronetworks.duckdns.org`**!
5. Keep this tab open — you will paste your Oracle VM's Public IP address here once created.

> [!TIP]
> **Alternative (Custom Domain):** If you later buy `sabronetworks.pk` or `sabronetworks.com` (for ~$5-$10/year), you can simply point its DNS **A Record** to your Oracle Cloud IP address.

---

### Step 2: Create Your Free Oracle Cloud Virtual Machine

1. Register at **[https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/)** (Oracle Cloud Always Free Tier).
2. Once logged into the Oracle Cloud Console:
   - Click **Create a VM Instance** (Compute).
   - Name: `sabro-networks-server`.
   - Image: Choose **Canonical Ubuntu 22.04 LTS** or **24.04 LTS**.
   - Shape: Choose **Always Free-eligible** (Ampere ARM A1 with 2 to 4 cores and 12-24GB RAM, or AMD VM.Standard.E2.1.Micro with 1GB RAM).
   - Under **Networking**: Ensure **Assign a public IPv4 address** is set to **Yes**.
   - Under **Add SSH keys**: Click **Save private key** (downloads a `.key` file to your computer — keep it safe).
   - Click **Create**.
3. Within 60 seconds, your VM will show **Running** with a **Public IP Address** (e.g. `140.238.xxx.xxx`).
4. Go back to your **DuckDNS** tab, enter this Public IP in the IP box next to `sabronetworks`, and click **update ip**.

---

### Step 3: Open Firewall Ports (Port 80 & 443)

In Oracle Cloud Console:
1. Go to your VM instance -> Click on the **Virtual Cloud Network (VCN)** link.
2. Click **Security Lists** -> Click **Default Security List for...**.
3. Click **Add Ingress Rules**:
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: `TCP`
   - **Destination Port Range**: `80,443`
   - Description: `HTTP and HTTPS for Sabro Networks`
4. Click **Add Ingress Rules**.

---

### Step 4: Upload Sabro Networks to Your Oracle VM

You can upload your files from your Windows PC using **WinSCP**, **FileZilla**, or standard **SSH/SCP**:

#### Using WinSCP (Easy Windows GUI):
1. Download and open **WinSCP**.
2. Host name: Your Oracle Public IP (or `sabronetworks.duckdns.org`).
3. User name: `ubuntu`
4. Click **Advanced** -> **SSH** -> **Authentication** -> select your downloaded Oracle `.key` file.
5. Click **Login**.
6. Drag and drop your `SABRO NETWORKS` folder to `/home/ubuntu/sabro_networks`.

---

### Step 5: Run 1-Click Automated Setup (`deploy_oracle.sh`)

Connect to your Oracle VM using PowerShell or PuTTY:
```bash
ssh -i path/to/your_oracle_key.key ubuntu@sabronetworks.duckdns.org
```

Once connected, run the automated setup script included in your project:
```bash
cd sabro_networks
chmod +x deploy_oracle.sh
sudo ./deploy_oracle.sh sabronetworks.duckdns.org
```

**What this automated script does in 60 seconds:**
- Installs Python 3, pip, venv, Nginx, Certbot, and UFW firewall.
- Sets up Gunicorn with 3 background workers.
- Creates an auto-restarting **Systemd service** (`sabro-networks.service`) so the app never shuts down, even if the VM reboots.
- Configures **Nginx** reverse proxy to serve static files and cache assets at lightning speed.

---

### Step 6: Activate Free Let's Encrypt SSL (HTTPS)

Once `deploy_oracle.sh` finishes, activate the official green padlock SSL certificate with one command:

```bash
sudo certbot --nginx -d sabronetworks.duckdns.org
```
- Enter your email address when prompted.
- Agree to terms (`Y`).
- Choose **Redirect all HTTP traffic to HTTPS** (`2`).

**Done!** Your portal is now live with bank-grade SSL encryption:
**`https://sabronetworks.duckdns.org`**

---

### Production Maintenance & Daily Operations

#### Useful Commands on Oracle Server:
- **Check Server Status**:
  ```bash
  sudo systemctl status sabro-networks
  ```
- **Restart Application**:
  ```bash
  sudo systemctl restart sabro-networks
  ```
- **View Live Application Logs**:
  ```bash
  sudo journalctl -u sabro-networks -f
  ```
- **Download Database Backup**:
  You can download the database backup anytime directly from the web portal at:
  `https://sabronetworks.duckdns.org/backup/db` (Admin login required).
