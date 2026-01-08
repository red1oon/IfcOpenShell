# How to Install PDF Terrain and Other Red1OON Bonsai Addons

Installation guide for Red1OON's enhanced Bonsai addons with PDF Terrain and other features.

**Prerequisites**: You already have Bonsai addon installed and running in Blender.

---

## Quick Install (Recommended)

**For users who want PDF Terrain feature:**

### Step 1: Update Bonsai to Red1OON's Branch

**Find your Bonsai addon location**:
```
Windows: C:\Users\<YourName>\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons\bonsai
macOS: ~/Library/Application Support/Blender/5.0/scripts/addons/bonsai
Linux: ~/.config/blender/5.0/scripts/addons/bonsai
```

**If you installed Bonsai via Git**:
```bash
cd <blender_addons>/bonsai
git remote add red1oon https://github.com/red1oon/IfcOpenShell
git fetch red1oon
git checkout red1oon/feature/IFC4_DB
```

**If you installed Bonsai manually** (downloaded zip):
1. Download Red1OON's enhanced Bonsai:
   - Go to: https://github.com/red1oon/IfcOpenShell
   - Click "Code" → "Download ZIP"
   - **OR** click branch dropdown → select "feature/IFC4_DB" → Download ZIP

2. Extract the zip file

3. Navigate to: `IfcOpenShell-feature-IFC4_DB/src/bonsai/bonsai/`

4. Copy this entire `bonsai` folder to your Blender addons directory (replace existing)

5. Restart Blender

### Step 2: Install Python Dependencies

**Open command prompt/terminal as Administrator**:

**Windows**:
```cmd
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install google-cloud-vision Pillow
```

**macOS**:
```bash
/Applications/Blender.app/Contents/Resources/5.0/python/bin/python3.11 -m pip install google-cloud-vision Pillow
```

**Linux**:
```bash
<blender_path>/5.0/python/bin/python3.11 -m pip install google-cloud-vision Pillow
```

### Step 3: Setup Google Vision API (First-time only)

**Get Credentials**:
1. Go to https://console.cloud.google.com/
2. Create new project (or use existing)
3. Enable "Cloud Vision API"
4. Go to "Credentials" → "Create Credentials" → "Service Account"
5. Create key → Download JSON file

**Set Environment Variable**:

**Windows** (PowerShell as Administrator):
```powershell
[System.Environment]::SetEnvironmentVariable('GOOGLE_APPLICATION_CREDENTIALS', 'C:\path\to\your-credentials.json', 'User')
```

**macOS/Linux** (add to ~/.bashrc or ~/.zshrc):
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-credentials.json"
```

**Restart Blender after setting environment variable!**

### Step 4: Verify Installation

1. Open Blender
2. Press `N` in 3D Viewport (sidebar)
3. Look for **"PDF Terrain"** tab
4. ✓ If you see it, installation successful!

---

## What You Get: Red1OON's Enhanced Features

### PDF Terrain Module (NEW)
- Extract elevation points from survey PDFs/PNGs
- Google Vision AI OCR integration
- Export to IFC for Revit/AutoCAD
- Location: N Panel → PDF Terrain

### Other Red1OON Features
*(List will grow as more addons are added)*

- **IFC4_DB Enhancements**: Database integration features
- *(More coming soon...)*

---

## Updating to Latest Red1OON Version

**If installed via Git**:
```bash
cd <blender_addons>/bonsai
git fetch red1oon
git pull red1oon feature/IFC4_DB
```
Restart Blender.

**If installed manually**:
- Download latest ZIP from https://github.com/red1oon/IfcOpenShell/tree/feature/IFC4_DB
- Replace `bonsai` folder
- Restart Blender

---

## Troubleshooting

### "PDF Terrain tab doesn't appear"

**Check**:
1. Bonsai addon is enabled: Edit → Preferences → Add-ons → Search "Bonsai" → ✓ Enabled
2. You installed from Red1OON's branch (not official IfcOpenShell)
3. Restart Blender after addon update

**Verify branch**:
```bash
cd <blender_addons>/bonsai
git remote -v
# Should show red1oon repo
git branch
# Should show feature/IFC4_DB or similar
```

### "ModuleNotFoundError: No module named 'google'"

**Fix**: Install Python dependencies (see Step 2 above)

**Common mistake**: Installing to system Python instead of Blender's Python
- Must use Blender's python.exe path!
- Windows: `C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe`

### "Google Vision credentials not found"

**Fix**: Set GOOGLE_APPLICATION_CREDENTIALS environment variable (see Step 3)

**Check**:
```bash
# Windows PowerShell
$env:GOOGLE_APPLICATION_CREDENTIALS

# macOS/Linux
echo $GOOGLE_APPLICATION_CREDENTIALS
```
Should show path to your credentials JSON file.

### Mixed with Official Bonsai

**Issue**: You have both official IfcOpenShell Bonsai and Red1OON's version

**Fix**: Use one or the other, not both
```bash
cd <blender_addons>/bonsai
git remote -v
# Remove official remote if you want to use Red1OON only
git remote remove origin
git remote add origin https://github.com/red1oon/IfcOpenShell
```

---

## Switching Back to Official Bonsai

If you want to return to official IfcOpenShell Bonsai:

```bash
cd <blender_addons>/bonsai
git remote add upstream https://github.com/IfcOpenShell/IfcOpenShell
git fetch upstream
git checkout upstream/v0.8.0  # or latest version
```

Restart Blender. PDF Terrain features will be removed.

---

## Links

- **Red1OON's Bonsai**: https://github.com/red1oon/IfcOpenShell
- **Branch**: feature/IFC4_DB
- **Issues**: https://github.com/red1oon/IfcOpenShell/issues
- **Official Bonsai**: https://github.com/IfcOpenShell/IfcOpenShell
- **OSArch Community**: https://community.osarch.org/

---

## Support

**For Red1OON-specific features** (PDF Terrain, etc.):
- GitHub Issues: https://github.com/red1oon/IfcOpenShell/issues
- Email: red1org@gmail.com

**For general Bonsai questions**:
- OSArch Forum: https://community.osarch.org/
- Official docs: https://docs.bonsaibim.org/

---

*This guide assumes you have Bonsai already installed and working. If not, install official Bonsai first from https://blenderbim.org/download.html*
