(() => {
  "use strict";

  const PROFILE_KEY = "zack-profile-v1";
  const get = (id) => document.getElementById(id);
  const onboarding = get("onboarding");
  const welcome = get("welcome");
  const form = get("profileForm");
  const nicknameInput = get("profileNickname");
  const emailInput = get("profileEmail");
  const error = get("profileError");
  let profile = readProfile();

  function readProfile() {
    try {
      const saved = JSON.parse(localStorage.getItem(PROFILE_KEY) || "null");
      if (saved && typeof saved.nickname === "string" && typeof saved.email === "string" &&
          saved.nickname.trim() && saved.nickname.trim().length <= 32 &&
          isValidEmail(saved.email.trim())) {
        return { ...saved, nickname: saved.nickname.trim(), email: saved.email.trim().toLowerCase() };
      }
    } catch (_) {}
    return null;
  }

  function isValidEmail(value) {
    return value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  function announce(name, detail) {
    if (typeof window !== "undefined" && typeof window.dispatchEvent === "function" && typeof CustomEvent === "function") {
      window.dispatchEvent(new CustomEvent(name, { detail }));
    }
  }

  function render() {
    const hasProfile = Boolean(profile);
    onboarding.hidden = hasProfile;
    welcome.hidden = !hasProfile;
    if (hasProfile) {
      get("welcomeTitle").textContent = `Welcome back, ${profile.nickname}.`;
      get("welcomeDetail").textContent = "Your workspace is saved on this device and ready when you are.";
    }
    announce("loki:profile", profile);
  }

  function openEditor() {
    nicknameInput.value = profile ? profile.nickname : "";
    emailInput.value = profile ? profile.email : "";
    error.textContent = "";
    onboarding.hidden = false;
    welcome.hidden = true;
    announce("loki:profile-edit");
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const nickname = nicknameInput.value.trim();
    const email = emailInput.value.trim().toLowerCase();
    if (!nickname || nickname.length > 32) {
      error.textContent = "Enter a nickname of 1–32 characters.";
      return;
    }
    if (!isValidEmail(email)) {
      error.textContent = "Enter a valid email address.";
      return;
    }
    const next = { nickname, email, saved_at: new Date().toISOString() };
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify(next));
    } catch (_) {
      error.textContent = "This browser could not save the profile. Check its storage settings.";
      return;
    }
    profile = next;
    render();
  });

  get("profileEdit").addEventListener("click", openEditor);
  get("profileForget").addEventListener("click", () => {
    try {
      localStorage.removeItem(PROFILE_KEY);
    } catch (_) {
      get("welcomeDetail").textContent = "This browser could not clear the saved profile. Try again.";
      return;
    }
    profile = null;
    openEditor();
  });

  render();
})();

