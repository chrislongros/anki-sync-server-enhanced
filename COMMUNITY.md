# Community Submissions

## Awesome Self-Hosted

Submit a PR to https://github.com/awesome-selfhosted/awesome-selfhosted

Add under `Software / Note-taking & Editors` section (alphabetically):

```markdown
- [Anki Sync Server Enhanced](https://github.com/chrislongros/anki-sync-server-enhanced) - Docker image for self-hosted Anki sync server with automated backups, Prometheus metrics, and notifications. Built from official Anki source. `AGPL-3.0` `Docker`
```

Or under `Software / Learning and Courses` if that section exists.

---

## Reddit r/selfhosted Post

Title: **Self-hosted Anki sync server with backups, metrics, and notifications**

Body:

```
I built a Docker image for running your own Anki sync server. It wraps the official Anki sync server with features useful for self-hosters:

**Why use this instead of building from source?**

| Feature | Build yourself | This image |
|---------|----------------|------------|
| Pre-built image | No | Yes |
| Auto-updates | Manual | Daily builds |
| Multi-arch | Manual | amd64 + arm64 |
| Automated backups | No | Yes |
| Prometheus metrics | No | Yes |
| Notifications | No | Discord/Telegram/Slack |

**Quick start:**

    docker run -d \
      --name anki-sync \
      -p 8080:8080 \
      -e SYNC_USER1=user:password \
      -v anki_data:/data \
      chrislongros/anki-sync-server-enhanced

Then in Anki: Tools > Preferences > Syncing > set server to http://your-ip:8080/

**Links:**
- GitHub: https://github.com/chrislongros/anki-sync-server-enhanced
- Docker Hub: https://hub.docker.com/r/chrislongros/anki-sync-server-enhanced

Works on TrueNAS SCALE, Unraid, Raspberry Pi, and any Docker host.

Feedback welcome!
```

---

## Reddit r/Anki Post

Title: **Docker image for self-hosted Anki sync (with backups and monitoring)**

Body:

```
For those who self-host their Anki sync server, I made a Docker image that adds some useful features on top of the official sync server:

- **Automated backups** with configurable retention
- **Multi-user support** (up to 99 users)
- **Prometheus metrics** for monitoring
- **Notifications** (Discord, Telegram, Slack) for server events
- **Auto-updates** when new Anki versions are released

**Quick start:**

    docker run -d -p 8080:8080 \
      -e SYNC_USER1=myuser:mypassword \
      -v anki_data:/data \
      chrislongros/anki-sync-server-enhanced

GitHub: https://github.com/chrislongros/anki-sync-server-enhanced

It's built from the official Anki source code, just with extras for self-hosters. Templates for TrueNAS and Unraid included.
```

---

## Anki Forums Post

Title: **Docker image for self-hosted sync server with backups**

Post in: Development or Add-ons

Body:

```
I've created a Docker image that wraps the official Anki sync server with additional features for self-hosters:

- Automated daily backups with retention policy
- Multi-user support
- Prometheus metrics endpoint
- Discord/Telegram/Slack notifications
- Multi-architecture (amd64, arm64)
- Auto-updates via GitHub Actions

It builds directly from the official ankitects/anki repository, just adds Docker infrastructure and ops features.

GitHub: https://github.com/chrislongros/anki-sync-server-enhanced
Docker Hub: docker pull chrislongros/anki-sync-server-enhanced

Templates for TrueNAS SCALE and Unraid are included.

Would appreciate any feedback or feature suggestions.
```

---

## Unraid Community Apps

To submit to Unraid Community Apps:

1. Fork https://github.com/Unraid-Community-Apps/unraid-templates
2. Add your template to a folder named after your GitHub username
3. Submit a PR

Your template file is at: `unraid/anki-sync-server.xml`
