# Google Email Setup

A Google account is required for setting up the email waitlist, as the app
programmatically sends emails for free from a Google email you supply.

1. It is recommended to create a dedicated Google account for your parking space monitor
system, so you can name the account/email something descriptive.

2. Log in to your account, go to the [Google Cloud
console](https://console.cloud.google.com/apis/credentials), create a Google Cloud
project for your app, set the Audience mode to "test", and create an OAuth client ID with
application type "Desktop App". Download the credentials file.

3. The park-it CLI provides a command for runnign initial Google OAuth flow via a web
   brower. Run `park-it oauth [credentials-file-path]` and sign in to generate a long-lived refresh token file.

4. Pass the path of that token file as an argument to [`build_app()`](reference/build_app.md). 

5. When you are ready to deploy, it is recommended to change your Google app Audience from "test" to
   "production", as this makes the refresh token last indefinitely. 
