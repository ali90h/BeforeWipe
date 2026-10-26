# One volunteer wanted: a safe first Alpha trial

BeforeWipe is an experimental local review aid for developer work. We need **one developer on macOS or Linux** who can read basic Git output and would like to help us understand whether its findings and limits are clear. No previous BeforeWipe experience is needed. No participant results exist yet.

**No wiping, deleting, cleanup, repository conversion, remote access, or uploads of project data. Keep every original. BeforeWipe must never decide whether a machine can be wiped.** Participation is optional; stop or decline any step without giving a reason.

## First session: invented data only, about 20–30 minutes

1. Express interest through this repository's **Issues → New issue → Volunteer for the first safe trial** form. Do not add contact details or project information. Your GitHub username and issue will be public. If you prefer not to post publicly, wait until a suitable private channel is available. The maintainer must reply and arrange supervision before any session; there is no automatic enrollment.
2. Read [README](../README.md) and [SECURITY](../SECURITY.md), check out the Alpha source, and run the 109 synthetic tests. Python 3.9+ and Git are required; use a currently supported Python version. Windows is unsupported.
3. With the facilitator, create a new synthetic demo from the source directory:

   ```sh
   python3 -B -m unittest discover -s tests -v
   python3 -B -m beforewipe demo --directory demo-work-volunteer
   python3 -B -m beforewipe assess --plan demo-work-volunteer/plan.json
   ```

   Choose a different new `demo-work-*` name if it already exists. Existing directories are refused. On macOS the checkout path must have no symlink ancestors. Exit 1 from assessment is expected: the demo deliberately contains unresolved findings. Do not run commands against your own project for this exercise.
4. Explain the findings in your own words. After reviewing the selected synthetic files in both demo copies as non-sensitive, separately choose whether to authorize their comparison:

   ```sh
   python3 -B -m beforewipe verify --plan demo-work-volunteer/plan.json --allow-content-read
   ```

   This permits selected-file reads only. It does not authorize Git object reads. The first exercise does not require `--allow-git-object-read`. The demo contains an intentionally mismatching copy and a missing selection, so exit 1 is expected here too.
5. Record time spent, confusing wording, a useful finding and any missed expectation. Public feedback must use only this synthetic exercise, via the **Synthetic pilot feedback** issue form. Never post a real plan, report, screenshot, transcript or file path. Nothing is automatically uploaded.

Before closing, explain why each answer is **no**: Can work outside the plan be found? Can unknown packed staging with zero reported changes be considered clean? Does complete staging or matching working-file content preserve an index-only version? Does a file match or exit 0 prove recovery or wipe safety?

## Optional later session with real work

This requires a **new, separate agreement**, the full [pilot procedure](PILOT.md), a trusted stable non-sensitive scope, and independent Git/recovery review. A volunteer issue is not data-access consent. Real plans, reports and worksheets stay under participant control; do not send or commit them. Record a local storage choice separately. Review and authorize exact roots first, optional Git-object reads separately, selected-file reads separately for both copies, and independent Git/restore work separately. Declining expanded reads is a valid outcome.

Packed/external objects, unsupported indexes, reflog-only work, excluded files, sessions, blobs/history, forgotten directories, backup provenance and off-device survival remain coverage gaps. A matching file can coexist with losing important staged versions or stashes. Do not change repositories to make the tool return a nicer result. Stop for unexpected access, changes to originals, or misunderstanding that a result approves wiping.

One synthetic session measures usability and comprehension only. A later real-data session can record independently confirmed overlooked risks and important misses; one person cannot establish broad usefulness or safety. There is no payment or turnaround commitment in this invitation.

## بالعراقي

نحتاج متطوع واحد يجرب الأداة ويانا على **بيانات وهمية فقط بالبداية**، بحدود 20–30 دقيقة. ما نفرمت، ما نحذف، وما نطلب ملفات مشاريعك أو محادثاتك. افتح issue من قالب التطوع بكلمة اهتمام فقط ومن دون بيانات شخصية؛ اسم حسابك راح يكون ظاهر. انتظر تنسيق المشرف قبل التجربة. الأداة ما تثبت أن فرمتة الجهاز آمنة، وحتى تطابق الملفات مو إذن بالمسح. أي تجربة لاحقة على شغلك تحتاج موافقات مستقلة وتبقى بياناتك عندك.
