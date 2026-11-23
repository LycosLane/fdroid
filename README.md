# LycosLane F-Droid Repository

Self-hosted F-Droid repository served via GitHub Pages for all Pure Suite Android applications (`PurePodcast`, `PureAudiobooks`, `PureMusic`, and `FreeDataDiet Mobile`).

---

## Add Repository to F-Droid Client

Open **F-Droid**, **Droid-ify**, or **Neo Store** and add the following repository URL:

`https://lycoslane.github.io/fdroid-repo/repo`

---

## One-Time GitHub Setup

1. Create a public GitHub repository named `fdroid-repo` under `LycosLane`.
2. Generate a dedicated repository signing keystore locally (keep this file backed up outside the repo):

   ```bash
   keytool -genkeypair -keystore fdroid-repo.p12 -storetype PKCS12 -alias repokey -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=LycosLane F-Droid Repo"
   ```

3. Base64-encode the keystore (single line, no wrapping) and add three GitHub repository secrets under **Settings -> Secrets and variables -> Actions**:
   - `FDROID_KEYSTORE_BASE64`: base64 contents of `fdroid-repo.p12`
   - `FDROID_KEYSTORE_PASS`: keystore password
   - `FDROID_KEY_PASS`: key password (same as keystore password for PKCS12)

4. Enable GitHub Pages under **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.
5. Push `main` and trigger **Deploy F-Droid Repository** in the **Actions** tab (it also runs automatically every day at `04:00 UTC`).

---

## License

MIT License © 2026 LycosLane
