"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../static/js/profile.js"), "utf8");
const key = "zack-profile-v1";

function makeRig(initialProfile = null, options = {}) {
  const elements = new Map();
  for (const id of ["onboarding", "welcome", "profileForm", "profileNickname", "profileEmail",
    "profileError", "welcomeTitle", "welcomeDetail", "profileEdit", "profileForget"]) {
    elements.set(id, {
      id, value: "", textContent: "", hidden: false, listeners: {},
      addEventListener(event, listener) { this.listeners[event] = listener; },
      checkValidity() { return this.value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.value); },
    });
  }
  const stored = new Map();
  if (initialProfile !== null) stored.set(key, typeof initialProfile === "string" ? initialProfile : JSON.stringify(initialProfile));
  const localStorage = {
    getItem(name) { return stored.has(name) ? stored.get(name) : null; },
    setItem(name, value) {
      if (options.failWrites) throw new Error("storage unavailable");
      stored.set(name, String(value));
    },
    removeItem(name) {
      if (options.failRemovals) throw new Error("storage unavailable");
      stored.delete(name);
    },
  };
  const document = { getElementById(id) { return elements.get(id); } };
  let networkCalls = 0;
  vm.runInNewContext(script, {
    document, localStorage, Date,
    fetch() { networkCalls += 1; },
  });
  return { elements, localStorage, stored, networkCalls: () => networkCalls };
}

test("first visit shows the required profile form", () => {
  const rig = makeRig();
  assert.equal(rig.elements.get("onboarding").hidden, false);
  assert.equal(rig.elements.get("welcome").hidden, true);
  assert.equal(rig.networkCalls(), 0);
});

test("saved profile welcomes the nickname on return", () => {
  const rig = makeRig({ nickname: "Alex", email: "alex@example.com" });
  assert.equal(rig.elements.get("onboarding").hidden, true);
  assert.equal(rig.elements.get("welcome").hidden, false);
  assert.equal(rig.elements.get("welcomeTitle").textContent, "Welcome back, Alex.");
});

test("saving trims the nickname, normalizes email and persists locally", () => {
  const rig = makeRig();
  rig.elements.get("profileNickname").value = "  Alex  ";
  rig.elements.get("profileEmail").value = " ALEX@Example.COM ";
  let prevented = false;
  rig.elements.get("profileForm").listeners.submit({ preventDefault() { prevented = true; } });
  const saved = JSON.parse(rig.localStorage.getItem(key));
  assert.equal(prevented, true);
  assert.equal(saved.nickname, "Alex");
  assert.equal(saved.email, "alex@example.com");
  assert.equal(rig.elements.get("welcomeTitle").textContent, "Welcome back, Alex.");
  assert.equal(rig.networkCalls(), 0);
});

test("invalid details are rejected without writing to storage", () => {
  const rig = makeRig();
  rig.elements.get("profileNickname").value = "   ";
  rig.elements.get("profileEmail").value = "not-an-email";
  rig.elements.get("profileForm").listeners.submit({ preventDefault() {} });
  assert.equal(rig.localStorage.getItem(key), null);
  assert.match(rig.elements.get("profileError").textContent, /nickname/);
});

test("invalid email is rejected even when nickname is valid", () => {
  const rig = makeRig();
  rig.elements.get("profileNickname").value = "Alex";
  rig.elements.get("profileEmail").value = "alex-at-example";
  rig.elements.get("profileForm").listeners.submit({ preventDefault() {} });
  assert.equal(rig.localStorage.getItem(key), null);
  assert.match(rig.elements.get("profileError").textContent, /valid email/i);
});

test("nickname over the supported length is rejected", () => {
  const rig = makeRig();
  rig.elements.get("profileNickname").value = "A".repeat(33);
  rig.elements.get("profileEmail").value = "alex@example.com";
  rig.elements.get("profileForm").listeners.submit({ preventDefault() {} });
  assert.equal(rig.localStorage.getItem(key), null);
  assert.match(rig.elements.get("profileError").textContent, /1–32/);
});

test("email over the supported length is rejected", () => {
  const rig = makeRig();
  rig.elements.get("profileNickname").value = "Alex";
  rig.elements.get("profileEmail").value = `${"a".repeat(244)}@example.com`;
  rig.elements.get("profileForm").listeners.submit({ preventDefault() {} });
  assert.equal(rig.localStorage.getItem(key), null);
  assert.match(rig.elements.get("profileError").textContent, /valid email/i);
});

test("edit and forget return the user to the onboarding form", () => {
  const rig = makeRig({ nickname: "Alex", email: "alex@example.com" });
  rig.elements.get("profileEdit").listeners.click();
  assert.equal(rig.elements.get("onboarding").hidden, false);
  assert.equal(rig.elements.get("profileEmail").value, "alex@example.com");
  rig.elements.get("profileForget").listeners.click();
  assert.equal(rig.localStorage.getItem(key), null);
  assert.equal(rig.elements.get("welcome").hidden, true);
  assert.equal(rig.elements.get("onboarding").hidden, false);
});

test("saving an edited profile replaces the previous local values", () => {
  const rig = makeRig({ nickname: "Alex", email: "alex@example.com" });
  rig.elements.get("profileEdit").listeners.click();
  rig.elements.get("profileNickname").value = "Jordan";
  rig.elements.get("profileEmail").value = "JORDAN@example.com";
  rig.elements.get("profileForm").listeners.submit({ preventDefault() {} });
  const saved = JSON.parse(rig.localStorage.getItem(key));
  assert.equal(saved.nickname, "Jordan");
  assert.equal(saved.email, "jordan@example.com");
  assert.equal(rig.elements.get("welcomeTitle").textContent, "Welcome back, Jordan.");
});

test("malformed stored data safely falls back to onboarding", () => {
  const rig = makeRig("{broken json");
  assert.equal(rig.elements.get("onboarding").hidden, false);
  assert.equal(rig.elements.get("welcome").hidden, true);
});

test("stored profiles with invalid fields safely fall back to onboarding", () => {
  const rig = makeRig({ nickname: " ".repeat(2), email: "not an email" });
  assert.equal(rig.elements.get("onboarding").hidden, false);
  assert.equal(rig.elements.get("welcome").hidden, true);
});

test("stored nickname is rendered as text, not interpreted as markup", () => {
  const rig = makeRig({ nickname: "<img src=x>", email: "alex@example.com" });
  assert.equal(rig.elements.get("welcomeTitle").textContent, "Welcome back, <img src=x>.");
});

test("storage write failure keeps the form open and reports the problem", () => {
  const rig = makeRig(null, { failWrites: true });
  rig.elements.get("profileNickname").value = "Alex";
  rig.elements.get("profileEmail").value = "alex@example.com";
  rig.elements.get("profileForm").listeners.submit({ preventDefault() {} });
  assert.equal(rig.elements.get("onboarding").hidden, false);
  assert.match(rig.elements.get("profileError").textContent, /could not save/i);
});

test("storage read failure safely shows onboarding", () => {
  const rig = makeRig();
  rig.localStorage.getItem = () => { throw new Error("storage unavailable"); };
  // Re-run in a fresh VM so the failing storage read occurs during initialization.
  const elements = new Map([...rig.elements].map(([id, element]) => [id, { ...element, listeners: {} }]));
  vm.runInNewContext(script, {
    document: { getElementById(id) { return elements.get(id); } },
    localStorage: { getItem() { throw new Error("storage unavailable"); } },
    Date,
  });
  assert.equal(elements.get("onboarding").hidden, false);
  assert.equal(elements.get("welcome").hidden, true);
});

test("storage remove failure keeps the saved welcome visible with an error", () => {
  const rig = makeRig({ nickname: "Alex", email: "alex@example.com" }, { failRemovals: true });
  rig.elements.get("profileForget").listeners.click();
  assert.equal(rig.elements.get("welcome").hidden, false);
  assert.match(rig.elements.get("welcomeDetail").textContent, /could not clear/i);
});

test("editing clears stale validation messages", () => {
  const rig = makeRig({ nickname: "Alex", email: "alex@example.com" });
  rig.elements.get("profileError").textContent = "Old error";
  rig.elements.get("profileEdit").listeners.click();
  assert.equal(rig.elements.get("profileError").textContent, "");
});

