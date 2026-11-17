# instagram-spotseason-carousels

Posts carousels to the Instagram account @spotseason twice a day, at about
8:00 am and 8:00 pm US Eastern, through Instagram's official API.

## How it works

1. Approved carousels sit in `queue/`, one folder each.
2. A GitHub Actions job wakes around each posting time and runs
   `scripts/publish.py`.
3. The script posts the first folder in `queue/` (in name order), then moves
   it to `posted/` with a `result.json` holding the link to the live post.

If `queue/` is empty, nothing is posted.

## A carousel folder

```
queue/
  0001-hard-conversation/
    01.jpg
    02.jpg
    ...
    07.jpg
    caption.txt
```

- Folder names start with a number, so they post in order.
- 2 to 10 slides, JPEG only, named so they sort in slide order.
- `caption.txt` holds the caption and hashtags: 2,200 characters and 30
  hashtags at most.
- Names use only letters, digits, dots, dashes and underscores.

## Drafts

New carousels start in `drafts/`, which is never posted from. Each draft
holds its slide designs in `slides/` plus a `caption.txt`. When slide designs
are pushed, the **Render draft slides** job turns them into 1080 x 1350 JPEGs
beside them. Once the owner approves a draft, its JPEGs and caption move to
`queue/` and its slide designs move to `archive/`.

## Pausing

Add an empty file named `PAUSED` to the top of the repository. Nothing posts
while it is there. Delete it to resume.

## Running by hand

Open the **Actions** tab, choose **Publish carousel**, then **Run workflow**.

- `dry-run` shows what would post next and changes nothing.
- `publish-now` posts the next carousel immediately.

## Things to know

- The Instagram access token lives in the repository secret
  `IG_ACCESS_TOKEN`. It is never written to a file or printed in a log.
- This repository is public because Instagram fetches each slide from a
  public address. Put nothing private in it.
- The posting times are kept by cron-job.org, which sends a `post-slot`
  event to GitHub at each slot. GitHub's own schedule is only a backup,
  because it often fires hours late or not at all.
- GitHub may start scheduled jobs late, or skip a wake-up, when it is busy.
  The job wakes every 20 minutes through each slot, and a slot stays open
  for three hours, so posts can land up to a few hours after the slot time.
- GitHub switches off schedules in a public repository after 60 days without
  activity. Pushing a new batch counts as activity.
- If a post goes live but the job fails before recording it, the same
  carousel would post again at the next slot. If a run shows a red cross
  after "Posted", add the `PAUSED` file and check the account first.
