# Build setup

The Python tooling uses the standard library. No pip packages are required.

Install Python 3.10 or newer, **Apktool 3.0.3** and a JDK providing `java`, `keytool` and `jarsigner`. Apktool is pinned because the patch expects a reviewed decoded source layout. Use the [official Apktool installation guide](https://apktool.org/docs/install/) and [release](https://github.com/iBotPeaches/Apktool/releases/tag/v3.0.3).

On macOS with Homebrew, the tested dependency setup was:

```sh
brew install apktool openjdk
export JAVA_HOME="$(brew --prefix openjdk)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
```

Check `apktool --version` against `profiles/p1.json`. A future package-manager version may differ; install the reviewed release rather than changing the profile to silence the check.

On Linux or Windows, install the same Apktool release and a JDK, then make those four tools available in your terminal. On Windows, use `py -3` instead of `python3` if that is your Python launcher. Build commands are otherwise the same.

From the repository directory:

```sh
python3 pairbridge.py fetch
python3 pairbridge.py verify-inputs
python3 pairbridge.py prepare
```

If you already have the exact inputs, place them in `inputs/` as `upstream.apk`, `left.bin` and `right.bin`, or use explicit paths:

```sh
python3 pairbridge.py prepare --apk /path/to/upstream.apk --left /path/to/left.bin --right /path/to/right.bin --out dist
```

`--firmware-only` builds the firmware files without requiring Java or rebuilding the APK. It does not create an Android app.

The build decodes the verified upstream APK into a temporary local directory, adds the guarded commit UI, rebuilds it, signs it locally and decodes the result again. It verifies unchanged FOTA SDK classes, unchanged permissions, the disabled debugging flag, the separate application package and the guard.

The Android package retains the upstream target SDK. Signing uses the RSA/SHA-256 APK v1 scheme that was accepted in the original local device test. Your local certificate makes your APK hash different from someone else's even when the firmware files match exactly. Keys are kept in `.local/signing/`; retain them privately if you want to rebuild an app update with the same signer.

Generated directories are ignored by Git. The preparation command never uses ADB, connects to a Bluetooth device or flashes hardware.

Run the source tests with:

```sh
python3 -m unittest discover -s tests -v
```
