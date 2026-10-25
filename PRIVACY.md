# 🔒 Privacy

**Short version:** you can use the app without signing in, and then nothing is saved on our servers. If you sign in, we save only your practice progress under a scrambled ID. We never store your email, name or photo, we show no ads, and we never sell data.

### What we store (only if you sign in)
- A **pseudonymous user ID**: an HMAC-SHA256 hash of your lowercased email, made with a secret key ("pepper") that only the server knows. It can't be reversed back into your email.
- Your **attempts**: question ID, topic, difficulty, whether you got it right, the trap type, time taken in seconds with its speed category, and a timestamp.
- Your **adaptive level** per topic (Easy / Moderate / CAT-Level).
- Your **streak**, today's **AI-question count**, your **error log / review queue**, and your **plan** (free/pro) with the **Pro expiry date**.
- During an upgrade, a **payment reference ID** (derived from your hashed ID) so the payment can be matched to your account.
- **Question reports** (when anyone presses "Report this question") are stored with only the topic, a question reference and the reason. No user ID is attached, so a report cannot be linked to you, and that includes signed-in users.

### What we never store
- Your email address, name or profile photo. Google sends them at sign-in; we use the email only in memory to compute the hash, then discard it.
- Card, UPI or bank details. Payments happen entirely on Razorpay's own page.
- Your IP address or device fingerprint (the app keeps no such logs).

### Guest mode
Without signing in, everything lives in your browser session and disappears when you close the tab.

### Third parties
- **Google** (sign-in only): verifies who you are. Governed by Google's privacy policy.
- **Google Gemini**: when you generate an AI question, we send the topic, difficulty and example questions from our seed bank. **No personal data is sent.**
- **Supabase**: hosts the database. Row Level Security is enabled and the public key has no access; only the app server can read or write.
- **Razorpay**: processes Pro payments. We only ask Razorpay whether a payment for your reference ID was completed.
- **Streamlit Community Cloud**: hosts the app.

### Your controls
- **Download my data:** a JSON export of everything we hold about you (Privacy tab).
- **Delete my data:** permanently deletes all your rows, immediately (Privacy tab, with a confirmation). This also removes Pro status.

### No ads, no selling
We don't show ads, don't sell or share data, and don't use your data to train models.

Questions: open an issue on the GitHub repository.
