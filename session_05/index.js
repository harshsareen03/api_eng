// server.js
// Run with: node server.js
// No external libs, no crypto, just http.createServer and JSON file as DB.

const http = require("http");
const fs = require("fs");

const PORT = 3000;
const DB_FILE = "users.json";

// Insecure demo JWT (base64 encode/decode only)
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

// Helpers
function readUsers() {
  if (!fs.existsSync(DB_FILE)) return [];
  return JSON.parse(fs.readFileSync(DB_FILE, "utf-8"));
}
function saveUsers(users) {
  fs.writeFileSync(DB_FILE, JSON.stringify(users, null, 2));
}

// Basic HTML
function homePage() {
  return `
<html><body>
  <h1>FaceLike (Minimal)</h1>
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

// Server
const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/") {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(homePage());
  }
  else if (req.method === "GET" && req.url === "/register") {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(registerPage());
  }
  else if (req.method === "GET" && req.url === "/profile") {
    const cookies = parseCookies(req);
    const token = cookies["access_token"];
    const payload = token && verifyToken(token);
    if (!payload) {
      res.writeHead(302, { Location: "/" });
      return res.end();
    }
    const users = readUsers();
    const user = users.find(u => u.email === payload.sub);
    if (!user) {
      res.writeHead(302, { Location: "/" });
      return res.end();
    }
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(profilePage(user));
  }
  else if (req.method === "POST" && req.url === "/register") {
    parseBody(req, body => {
      const { name, email, password } = body;
      let users = readUsers();
      if (users.find(u => u.email === email)) {
        res.writeHead(302, { Location: "/register" });
        return res.end();
      }
      users.push({ name, email, password });
      saveUsers(users);
      const token = createToken({ sub: email });
      res.writeHead(302, { "Set-Cookie": `access_token=${token}; HttpOnly`, Location: "/profile" });
      res.end();
    });
  }
  else if (req.method === "POST" && req.url === "/login") {
    parseBody(req, body => {
      const { email, password } = body;
      const users = readUsers();
      const user = users.find(u => u.email === email && u.password === password);
      if (!user) {
        res.writeHead(302, { Location: "/" });
        return res.end();
      }
      const token = createToken({ sub: email });
      res.writeHead(302, { "Set-Cookie": `access_token=${token}; HttpOnly`, Location: "/profile" });
      res.end();
    });
  }
  else if (req.method === "POST" && req.url === "/logout") {
    res.writeHead(302, { "Set-Cookie": "access_token=; Max-Age=0", Location: "/" });
    res.end();
  }
  else {
    res.writeHead(404);
    res.end("Not Found");
  }
});

// Helpers to parse
function parseCookies(req) {
  const list = {};
  const cookieHeader = req.headers.cookie;
  if (!cookieHeader) return list;
  cookieHeader.split(";").forEach(cookie => {
    let parts = cookie.split("=");
    list[parts[0].trim()] = decodeURIComponent(parts[1]);
  });
  return list;
}

function parseBody(req, callback) {
  let body = "";
  req.on("data", chunk => { body += chunk.toString(); });
  req.on("end", () => {
    const params = new URLSearchParams(body);
    const result = {};
    for (let [k, v] of params) result[k] = v;
    callback(result);
  });
}

server.listen(PORT, () => console.log(`Server running at http://localhost:${PORT}`));
