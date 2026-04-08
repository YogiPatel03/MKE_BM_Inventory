# Cost Notes

## Monthly Cost: $0

| Service | What it provides | Free tier limits | Risk |
|---|---|---|---|
| GitHub | Source control, Actions CI/CD | 2000 Actions minutes/month (private) | Unlikely to exceed for this team |
| Vercel | Frontend hosting | Unlimited bandwidth, 100 GB-hours serverless | None for a static React app |
| Render (free) | Backend hosting | 750 hours/month, sleeps after 15 min | Cold starts; see below |
| Neon.tech | PostgreSQL | 0.5 GB storage, 1 compute unit | 0.5 GB is ~500K rows of modest data |
| Telegram | Bot, notifications, photo storage | Unlimited | None |
| Sentry | Error tracking | 5,000 errors/month | None for 15 users |

## The One Real Tradeoff: Render Cold Starts

Render's free tier spins the backend down after 15 minutes of inactivity. The first request after sleeping takes 20-30 seconds.

For a small internal team:
- Morning first-open: slow (one person)
- During working hours with regular use: stays warm
- This is **acceptable for an internal tool**

**If cold starts become unacceptable:** Upgrade to Render Starter at $7/month for an always-on instance. This is the only realistic paid upgrade this system will ever need.

## Storage Budget

At 15 users doing ~5 transactions/day:
- ~100 transaction rows/day
- ~36,000 rows/year
- At ~500 bytes/row average: ~18 MB/year
- Neon free tier (0.5 GB) covers **27 years of this usage**

Photos are stored on Telegram's servers at no cost. No photo storage is provisioned in this system.

## GitHub Actions Usage

Estimated minutes/month:
- Backend CI: ~4 min/run × 20 pushes = 80 minutes
- Frontend CI: ~3 min/run × 20 pushes = 60 minutes
- Deploy: ~1 min/run × 10 deploys = 10 minutes
- Total: ~150 minutes (well within 2000 free minutes)

## Upgrade Path

| Trigger | Upgrade | Cost |
|---|---|---|
| Cold starts annoying | Render Starter | $7/month |
| Need in-app photos | Cloudinary free (25 GB) | $0 → $0 first |
| Database > 0.5 GB | Neon Launch | $19/month |
| Team grows significantly | Render Standard | $25/month |

Realistic path to paid: only if the team grows significantly or cold starts become a blocking issue. For 15 users, the $0 stack should work indefinitely.
