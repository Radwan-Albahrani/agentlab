"""Pull request review and QA for any companion: it works with whatever a GitHub App can see, so the bot's
installations decide which repos and PRs exist for it (install the App on another repo and its PRs appear).
Nothing listens or polls: the list is fetched when someone looks, and a review starts when someone asks.

github    the App: a short-lived JWT, then an installation token per account, cached until it expires
pulls     open PRs across every installation (one search each), the facts a review needs, and publishing:
          one comment-only review, a QA report with screenshots, a +1 when clean, resolving fixed threads
prompt    the lead chat's brief: lanes and QA as T3 child threads, then verification, then review.json
report    review.json -> inline comments that land on diff lines (anything else goes in the review body)

The companion decides where the review runs (its linked agent) and how it is asked for (page, Slack, ...)."""
