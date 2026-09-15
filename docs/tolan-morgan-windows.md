# Loading the Tolan Morgan sermons from Windows

Twenty-one sermons, start to finish, in about ten minutes. Everything below is
PowerShell.

## What this avoids

Pasting transcripts into a chat and having them retyped. The bodies come
straight from YouTube's caption track, so what lands in the database is the
delivered text rather than a copy of a copy.

## 1. Get the tools

    winget install Python.Python.3.12
    winget install yt-dlp.yt-dlp

Close and reopen PowerShell so both land on your PATH, then check:

    python --version
    yt-dlp --version

Install the one Python dependency:

    pip install requests

## 2. Get the code

    cd $HOME\dev
    git clone https://github.com/dontebee/gc3-sermon-library.git
    cd gc3-sermon-library
    git checkout claude/gc3-exemplar-corpus-ingest-quw6bt

Already have the clone:

    cd $HOME\dev\gc3-sermon-library
    git fetch origin
    git checkout claude/gc3-exemplar-corpus-ingest-quw6bt
    git pull

## 3. The service key

Doppler project `gc3-intranet`, config `prd`. For this window only:

    $env:SUPABASE_SERVICE_ROLE_KEY = "eyJ..."

Paste it between the quotes. It is gone when you close the window, which is
the point: it never reaches a file, a repo or a chat.

## 4. Fetch

    python fetch_tolan_morgan.py

One line per sermon as it goes, with the character count. Two of them sit
inside full-service videos and get trimmed to where the sermon starts (Signs
of Life at 29:00, How to Stop the Bleeding at 1:38:00). Anything it cannot
reach is named at the end with the reason, and the rest still load.

Output is `tolan_morgan_sermons.csv`.

## 5. Look before you write

    python exemplar_ingest.py --file tolan_morgan_sermons.csv `
        --preacher "Tolan Morgan" --ministry "Fellowship Bible Baptist Church"

Dry run. Read the skip list. Nothing is written.

## 6. Write

    python exemplar_ingest.py --file tolan_morgan_sermons.csv `
        --preacher "Tolan Morgan" --ministry "Fellowship Bible Baptist Church" `
        --apply

Safe to run twice. The unique index means a sermon already in the table is
skipped, not duplicated, so a partial run is repaired by running it again.

## 7. Prove it landed whole

    python exemplar_ingest.py --file tolan_morgan_sermons.csv `
        --preacher "Tolan Morgan" --verify-out verify_morgan.sql

Run `verify_morgan.sql` in the Supabase SQL editor. **Zero rows is the pass.**
Any row it returns is missing or short, and re-running step 6 repairs it.

Then the check that matters, also in the SQL editor:

```sql
select count(*) as contamination
from sermons
where speaker in (select distinct preacher from exemplar_sermons);
```

It must return 0.

## Two already in

Touch Me Again and It's About That Time were loaded by hand from pasted text.
The fetch will skip them rather than duplicate them. Their `source_file` reads
`pasted transcript, noiz.io, 2026-09-15` instead of the CSV name, which is how
you can tell them apart later.

## One sermon has no title yet

`uZI2JVvGWM0` is in the list with no title, so the fetch takes YouTube's own.
Rename it afterwards if YouTube's title is not what the sermon should be
called:

```sql
update exemplar_sermons
   set title = 'The title you want', notes = 'Scripture: ...'
 where source_video_id = 'uZI2JVvGWM0';
```

## If yt-dlp gets rate limited

Export a cookies.txt from a signed-in browser, then:

    $env:YT_COOKIES = "C:\path\to\cookies.txt"

The fetch picks it up automatically.

## Adding more

Add a line to `SERMONS` in `fetch_tolan_morgan.py`:

    ("VIDEOID", "Sermon Title", "Book 1:1-10", None),

Last field is a start offset in seconds, for a sermon inside a full service;
`None` means take the whole video. Then run steps 4 to 7 again.
