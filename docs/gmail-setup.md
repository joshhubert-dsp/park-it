# Google Email Setup

A Google account is required for setting up the email waitlist, as the app
programmatically sends emails for free from a Google email you supply.

1. It is recommended to create a dedicated Google account for your parking space monitor
   system, so you can name the account/email something descriptive.

2. Log in to your account, and create a Google Cloud
   [project](https://console.cloud.google.com/projectcreate) for
   your app.

3. Initialize the [Auth Platform](https://console.cloud.google.com/auth/overview) for
   your project.

4. Set [Publishing status](https://console.cloud.google.com/auth/audience) to "In
   production". This is the most convenient option and is secure as long as you keep
   your credentials file safe. "Testing" mode works too but limits refresh token
   lifetime to only 7 days rather than indefinite, and requires registering your email as
   an allowed user.

5. Create an [OAuth client ID](https://console.cloud.google.com/auth/clients) with
   application type "Desktop App". Download the credentials file.

6. Enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) for your
   project.

7. Go to [Data Access](https://console.cloud.google.com/auth/scopes) and add the scope
   `../auth/gmail.send`. You now have the proper setup for Google to allow programmatically
    sending emails using your client ID.

8. The park-it CLI provides a
   [command](https://joshhubert-dsp.github.io/park-it/cli/#park_it-oauth) for running
   the initial Google OAuth flow via a web brower. Run `park-it oauth
   [credentials-file-path]` and sign in to generate a long-lived refresh token file.

9. Pass the path of that token file as an argument to [`build_app()`](reference/build_app.md). 

