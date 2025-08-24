const express = require("express");
const fs = require("fs");
const cookieParser = require("cookie-parser");

const app = express();
const PORT = 3000;
const DB_FILE = "users.json";

// Middleware
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());

// Helpers
function readUsers() {
  if (!fs.existsSync(DB_FILE)) return [];
  return JSON.parse(fs.readFileSync(DB_FILE, "utf-8"));
}
function saveUsers(users) {
  fs.writeFileSync(DB_FILE, JSON.stringify(users, null, 2));
}

// Insecure demo JWT (just base64, no signature)
function createToken(payload) {
  const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64");
  return `${header}.${body}.`;
}
function verifyToken(token) {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    return JSON.parse(Buffer.from(parts[1], "base64").toString());
  } catch (e) {
    return null;
  }
}

// Views
function homePage() {
  return `
<html><body>
  <h1>FaceLike (Express)</h1>
  <form method="POST" action="/login">
    <input name="email" placeholder="Email">
    <input name="password" type="password" placeholder="Password">
    <button>Login</button>
  </form>
  <a href="/register">Register</a>
</body></html>`;
}

function registerPage() {
  return `
<html><body>
  <h1>Register</h1>
  <form method="POST" action="/register">
    <input name="name" placeholder="Full name">
    <input name="email" placeholder="Email">
    <input name="password" type="password" placeholder="Password">
    <button>Sign Up</button>
  </form>
  <a href="/">Back</a>
</body></html>`;
}

function profilePage(user) {
  return `
<html><body>
  <h1>Hello, ${user.name}</h1>
  <p>Email: ${user.email}</p>
  <form method="POST" action="/logout"><button>Logout</button></form>
</body></html>`;
}

// Routes
app.get("/", (req, res) => res.send(homePage()));

app.get("/register", (req, res) => res.send(registerPage()));

app.get("/profile", (req, res) => {
  const token = req.cookies["access_token"];
  const payload = token && verifyToken(token);
  if (!payload) return res.redirect("/");
  const users = readUsers();
  const user = users.find(u => u.email === payload.sub);
  if (!user) return res.redirect("/");
  res.send(profilePage(user));
});

app.post("/register", (req, res) => {
  const { name, email, password } = req.body;
  let users = readUsers();
  if (users.find(u => u.email === email)) return res.redirect("/register");
  users.push({ name, email, password });
  saveUsers(users);
  const token = createToken({ sub: email });
  res.cookie("access_token", token, { httpOnly: true });
  res.redirect("/profile");
});

app.post("/login", (req, res) => {
  const { email, password } = req.body;
  const users = readUsers();
  const user = users.find(u => u.email === email && u.password === password);
  if (!user) return res.redirect("/");
  const token = createToken({ sub: email });
  res.cookie("access_token", token, { httpOnly: true });
  res.redirect("/profile");
});

app.post("/logout", (req, res) => {
  res.clearCookie("access_token");
  res.redirect("/");
});

// Start server
app.listen(PORT, () => console.log(`🚀 Server running at http://localhost:${PORT}`));
