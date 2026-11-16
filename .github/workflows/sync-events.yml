name: Update Pokémon GO events

on:
  workflow_dispatch:
  schedule:
    # Daily at 05:17 UTC; GitHub sometimes delays scheduled runs.
    - cron: '17 5 * * *'

permissions:
  contents: write

concurrency:
  group: update-mega-events
  cancel-in-progress: false

jobs:
  update-events:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout the public website
        uses: actions/checkout@v4
      - name: Install Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Refresh events from Leek Duck mirror
        run: python scripts/update_events.py
      - name: Commit new event data when it changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/live-events.json
          if ! git diff --cached --quiet; then
            git commit -m "Refresh Pokémon GO event calendar"
            git push
          else
            echo "No new event data to publish"
          fi
