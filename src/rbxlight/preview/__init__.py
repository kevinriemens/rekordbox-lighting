"""preview package — rig layout description, program extraction, preview
payload construction, and self-contained document rendering.

Read-only, offline feature: turns a stored macro + a venue's fixture patch
+ an editable on-disk rig layout description into a payload matching the
agreed JSON contract, and a single self-contained HTML document embedding
that payload. Never opens a database read-write; always reads from the
working copy, never from live.
"""
