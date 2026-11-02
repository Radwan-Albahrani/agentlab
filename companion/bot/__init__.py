"""The companion: one person's agent in Slack. Start with `python3 -m bot`; the flow is described in each module:

main       start-up and the poller           routing   which Slack message goes where
tasks      Slack thread <-> T3 chat           errands   work done for someone else, as the owner
outbox     the gate for what the agent hands  requests  the owner's tags and colleagues asking them
drafts     product-update previews            publish   what the hub shows
asks       requests typed on the hub          posts     a message or poll for a channel, after the owner's OK
polls      polls the companion runs: votes, closing, the winner
reviews    pull request review and QA (the generic part is in reviewer/)
slack, t3, projects, prompts, text, state, jobs, config: the building blocks"""
