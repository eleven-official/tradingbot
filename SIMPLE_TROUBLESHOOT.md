# 🔧 LOKI - QUICK TROUBLESHOOTING GUIDE

## ❌ "Can't find Loki in Windows Search"

### **Solution 1: Use Full Name**
Instead of searching "Loki", try:
- "Loki Trading"
- "Loki Trading Platform"

### **Solution 2: Wait for Windows Indexing**
Windows needs 5-10 minutes to index new apps.
- Restart your computer
- Wait 10 minutes
- Try searching again

### **Solution 3: Use Start Menu Directly**
1. Click Start Menu
2. Scroll to "L"
3. Find "Loki Trading" folder
4. Click to open

### **Solution 4: Use Desktop Shortcut**
After running FIX_AND_TEST_EVERYTHING.bat, you'll have a desktop shortcut.
Just double-click it!

---

## ❌ "Python not found"

### **Solution:**
1. Download Python from: https://www.python.org/downloads/
2. During installation, CHECK THE BOX: "Add Python to PATH"
3. Restart computer
4. Run FIX_AND_TEST_EVERYTHING.bat again

---

## ❌ "Module not found" errors

### **Solution:**
```batch
pip install PyQt6 pyqtgraph pandas numpy matplotlib plotly
```

If that doesn't work:
```batch
python -m pip install --upgrade pip
pip install --upgrade PyQt6 pyqtgraph pandas numpy
```

---

## ❌ "Loki won't start"

### **Solution 1: Test Mode**
Double-click: `TEST_LOKI.bat`
This will show you any errors.

### **Solution 2: Check Dependencies**
```batch
python -c "from PyQt6.QtWidgets import QApplication; print('OK')"
```

If this gives an error, reinstall PyQt6:
```batch
pip uninstall PyQt6
pip install PyQt6
```

### **Solution 3: Use Simpler Version**
If enhanced app doesn't work, the original app.py should still work:
```batch
python -m loki.desktop.app
```

---

## ❌ "Charts not showing"

### **Solution:**
```batch
pip install pyqtgraph
```

Charts require pyqtgraph. Without it, you'll see placeholders (which is fine!).

---

## ✅ QUICK FIX FOR EVERYTHING

### **Just run this:**
```batch
FIX_AND_TEST_EVERYTHING.bat
```

This will:
- Check Python installation
- Install all dependencies
- Create all shortcuts
- Register with Windows
- Test everything
- Launch Loki

---

## 📱 HOW TO LAUNCH LOKI (4 WAYS)

### **Method 1: Desktop Shortcut**
Double-click "Loki Trading" on Desktop

### **Method 2: Start Menu**
Start Menu > Loki Trading Platform

### **Method 3: Batch File**
Double-click: `START_LOKI.bat`

### **Method 4: Windows Search**
1. Press Windows Key
2. Type "Loki Trading"
3. Click result

---

## 🆘 STILL NOT WORKING?

### **Last Resort - Manual Start:**
1. Open Command Prompt
2. Navigate to Loki folder:
   ```
   cd "C:\Users\MatheJ3\OneDrive - CEDR\tradingbot"
   ```
3. Run:
   ```
   python launch_loki.py
   ```
4. If you see errors, copy and paste them

### **Common Error Messages:**

**"No module named 'PyQt6'"**
- Run: `pip install PyQt6`

**"No module named 'loki'"**
- You're in the wrong directory
- Use: `cd` to navigate to tradingbot folder

**"Python was not found"**
- Python not installed or not in PATH
- Reinstall Python with "Add to PATH" checked

---

## ✅ VERIFICATION CHECKLIST

After running FIX_AND_TEST_EVERYTHING.bat, you should have:

- [ ] Python installed and working
- [ ] PyQt6 installed
- [ ] Desktop shortcut "Loki Trading"
- [ ] Start Menu entry
- [ ] START_LOKI.bat file
- [ ] TEST_LOKI.bat file
- [ ] launch_loki.py file

---

## 💡 PRO TIPS

1. **Always use FIX_AND_TEST_EVERYTHING.bat first**
2. **Use TEST_LOKI.bat to see errors**
3. **Desktop shortcut is most reliable**
4. **Windows Search needs time to index**
5. **Full search term works better: "Loki Trading Platform"**

---

## 📞 QUICK COMMANDS

```batch
# Fix everything
FIX_AND_TEST_EVERYTHING.bat

# Test with error messages
TEST_LOKI.bat

# Quick launch
START_LOKI.bat

# Install dependencies
pip install PyQt6 pyqtgraph pandas numpy

# Check Python
python --version

# Check imports
python -c "from PyQt6.QtWidgets import QApplication; print('OK')"
```

---

## ✅ IF ALL ELSE FAILS

Use the simple original desktop app:
```batch
python -c "from loki.desktop.app import main; main()"
```

This doesn't require pyqtgraph and is more basic but reliable.

---

**Most issues are fixed by running: FIX_AND_TEST_EVERYTHING.bat**

**Then restart your computer for Windows Search to work!**
