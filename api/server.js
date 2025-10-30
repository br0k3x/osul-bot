const fs = require('fs'),
    http = require('http'),
    https = require('https'),
    express = require('express'),
    cors = require('cors'),
    dotenv = require('dotenv');

const { REST } = require('@discordjs/rest');
const { Routes } = require('discord-api-types/v10');

// robust fetch wrapper: prefer global fetch (Node 18+). If not present, dynamically import node-fetch.
let fetch = globalThis.fetch;
if (!fetch) {
  let _nodeFetch = null;
  fetch = async (...args) => {
    if (!_nodeFetch) {
      const mod = await import('node-fetch');
      _nodeFetch = mod.default || mod;
      console.log("[API] Using node-fetch as fetch implementation fallback.");
    }
    return _nodeFetch(...args);
  };
}
dotenv.config({ path: __dirname + '/../internal/.env' });
const app = express();
app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json());

const OSU_CLIENT_ID = process.env.OSU_CLIENT_ID;
const OSU_CLIENT_SECRET = process.env.OSU_CLIENT_SECRET;
const API_BASE_URL = process.env.API_BASE_URL || 'https://stats.br0k3x.info/api';
const CALLBACK_URI = process.env.CALLBACK_URI;
const MONGODB_CONNECTION_STRING = process.env.MONGODB_CONNECTION_STRING;
const DISCORD_BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
const DISCORD_GUILD_ID = process.env.DISCORD_GUILD_ID;
const DISCORD_VERIFIED_ROLE_ID = process.env.DISCORD_VERIFIED_ROLE_ID;
const DISCORD_MEMBER_ROLE_ID = process.env.DISCORD_MEMBER_ROLE_ID;

// Template HTML routes - serve with environment variable substitution
app.get('/', (req, res) => {
  const htmlPath = __dirname + '/../index.html';
  fs.readFile(htmlPath, 'utf8', (err, data) => {
    if (err) return res.status(500).send('Error loading page');
    
    const rendered = data
      .replace(/45196/g, OSU_CLIENT_ID)
      .replace(/https:\/\/osul\.br0k3\.me\/oauth\/osu\/callback/g, CALLBACK_URI);
    
    res.send(rendered);
  });
});

app.get('/oauth/osu/callback', (req, res) => {
  const htmlPath = __dirname + '/../oauth/osu/callback.html';
  fs.readFile(htmlPath, 'utf8', (err, data) => {
    if (err) return res.status(500).send('Error loading page');
    
    const rendered = data
      .replace(/45196/g, OSU_CLIENT_ID)
      .replace(/https:\/\/stats\.br0k3x\.info\/api/g, API_BASE_URL)
      .replace(/https:\/\/osul\.br0k3\.me\/oauth\/osu\/callback/g, CALLBACK_URI);
    
    res.send(rendered);
  });
});

app.use(express.static(__dirname + '/..', { dotfiles: 'allow' }));

const port = process.env.PORT || 3002;

// Check if SSL files exist
const sslKeyPath = __dirname + '/ssl/private.key';
const sslCertPath = __dirname + '/ssl/certificate.crt';
const sslCaPath = __dirname + '/ssl/ca_bundle.crt';

let server;
if (fs.existsSync(sslKeyPath) && fs.existsSync(sslCertPath) && fs.existsSync(sslCaPath)) {
  const options = {
    key: fs.readFileSync(sslKeyPath),
    cert: fs.readFileSync(sslCertPath),
    ca: fs.readFileSync(sslCaPath),
    requestCert: false,
    rejectUnauthorized: false
  };
  server = https.createServer(options, app).listen(port, function(){
    console.log("osu!lounge SSL server listening on port " + port);
  });
} else {
  console.log("SSL certificates not found, starting HTTP server instead");
  server = http.createServer(app).listen(port, function(){
    console.log("osu!lounge HTTP server listening on port " + port);
  });
}

const { MongoClient } = require('mongodb');

let mongoClient = null;
let osuLoungeUsersCollection = null;

async function initMongo() {
  const uri = MONGODB_CONNECTION_STRING;
  if (!uri) {
    console.log('No MongoDB URI configured. DB features disabled.');
    return;
  }

  try {
    mongoClient = new MongoClient(uri, { useNewUrlParser: true, useUnifiedTopology: true });
    await mongoClient.connect();
    const dbName = 'main';
    const db = mongoClient.db(dbName);
    osuLoungeUsersCollection = db.collection('users');
    console.log('Connected to MongoDB for osu!lounge - ', dbName);
  } catch (err) {
    console.error('MongoDB connection error:', err.message);
  }
}

initMongo();

app.get('/api', async (req, res) => {
  res.status(200).json({ 
    status: 'active', 
    api: {
      "url": API_BASE_URL, 
      "version": "v1.0", 
      "database": "community-mongoatl",
      "endpoints": {
        "oauth": {
          "callback": {"name": "/api/oauth/osu/callback", "description": "Handle osu! OAuth callback"},
          "refresh": {"name": "/api/oauth/osu/refresh", "description": "Refresh osu! OAuth token"},
          "link": {"name": "/api/oauth/osu/link/discord", "description": "Link Discord account with osu!"}
        },
        "discord": {
          "search": {"name": "/api/discord/search-user", "description": "Search for Discord user by username"}
        }
      }
    }
  });
});

// osu! OAuth callback
app.post('/api/oauth/osu/callback', async (req, res) => {
  const { code, state } = req.body;
  
  if (!code || !state) {
    return res.status(400).json({ error: 'Missing code or state parameter' });
  }

  try {
    const tokenResponse = await fetch('https://osu.ppy.sh/oauth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: OSU_CLIENT_ID,
        client_secret: OSU_CLIENT_SECRET,
        code: code,
        redirect_uri: CALLBACK_URI,
        grant_type: 'authorization_code',
      })
    });

    if (!tokenResponse.ok) {
      const errorBody = await tokenResponse.text();
      console.error('osu! OAuth token error:', errorBody);
      return res.status(tokenResponse.status).json({ 
        error: 'OAuth token exchange failed', 
        details: errorBody,
        status: tokenResponse.status
      });
    }

    const tokens = await tokenResponse.json();

    res.status(200).json({ 
      success: true,
      tokens: tokens
    });
  } catch (err) {
    console.error('osu! OAuth callback error:', err);
    res.status(500).json({ error: 'OAuth callback failed', details: err.message });
  }
});

// osu! OAuth token refresh
app.post('/api/oauth/osu/refresh', async (req, res) => {
  const { refresh_token } = req.body;

  if (!refresh_token) {
    return res.status(400).json({ error: 'Missing refresh_token parameter' });
  }

  try {
    const tokenResponse = await fetch('https://osu.ppy.sh/oauth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: OSU_CLIENT_ID,
        client_secret: OSU_CLIENT_SECRET,
        refresh_token: refresh_token,
        grant_type: 'refresh_token',
      })
    });

    if (!tokenResponse.ok) {
      const errorBody = await tokenResponse.text();
      console.error('osu! OAuth token error:', errorBody);
      return res.status(tokenResponse.status).json({
        error: 'OAuth token exchange failed',
        details: errorBody,
        status: tokenResponse.status
      });
    }

    const tokens = await tokenResponse.json();

    res.status(200).json({
      success: true,
      tokens: tokens
    });
  } catch (err) {
    console.error('osu! OAuth refresh error:', err);
    res.status(500).json({ error: 'OAuth refresh failed', details: err.message });
  }
});

// Link Discord account with osu!
app.post('/api/oauth/osu/link/discord', async (req, res) => {
  const { id, osu_token, osu_refresh } = req.body;
  if (!id || !osu_token || !osu_refresh) {
    return res.status(400).json({ error: 'Missing id, osu_token, or osu_refresh parameter' });
  }
  if (!osuLoungeUsersCollection) {
    return res.status(500).json({ error: 'Database not connected' });
  }

  try {
    const filter = { discordId: id };
    
    // Check if document exists
    const existingDoc = await osuLoungeUsersCollection.findOne(filter);
    
    if (existingDoc) {
      // Document exists, update it
      const update = {
        $set: {
          osuAccessToken: osu_token,
          osuRefreshToken: osu_refresh,
          linkedAt: new Date()
        }
      };
      await osuLoungeUsersCollection.updateOne(filter, update);
    } else {
      // Document doesn't exist, create it
      const newDoc = {
        discordId: id,
        osuAccessToken: osu_token,
        osuRefreshToken: osu_refresh,
        linkedAt: new Date()
      };
      await osuLoungeUsersCollection.insertOne(newDoc);
    }
    
    // Assign Discord role after successful linking
    if (DISCORD_BOT_TOKEN && DISCORD_GUILD_ID && DISCORD_VERIFIED_ROLE_ID) {
      try {
        const rest = new REST({ version: '10' }).setToken(DISCORD_BOT_TOKEN);
        await rest.put(
          Routes.guildMemberRole(DISCORD_GUILD_ID, id, DISCORD_VERIFIED_ROLE_ID),
        );
        if (DISCORD_MEMBER_ROLE_ID) {
          await rest.put(
            Routes.guildMemberRole(DISCORD_GUILD_ID, id, DISCORD_MEMBER_ROLE_ID),
          );
        }
        console.log(`Assigned roles to Discord user ${id}`);
      } catch (discordErr) {
        console.error('Failed to assign Discord roles:', discordErr);
      }
    }
    
    res.status(200).json({ success: true, message: 'Discord account linked successfully' });
  } catch (err) {
    console.error('osu! Discord link error:', err);
    res.status(500).json({ error: 'Failed to link Discord account', details: err.message });
  }
});

// Discord user search endpoint
app.post('/api/discord/search-user', async (req, res) => {
  const { username } = req.body;
  
  if (!username) {
    return res.status(400).json({ error: 'Username is required' });
  }
  
  if (!DISCORD_BOT_TOKEN || !DISCORD_GUILD_ID) {
    return res.status(500).json({ error: 'Discord bot not configured' });
  }
  
  try {
    const rest = new REST({ version: '10' }).setToken(DISCORD_BOT_TOKEN);
    
    // Get all guild members
    const members = await rest.get(
      Routes.guildMembers(DISCORD_GUILD_ID) + '?limit=1000'
    );
    
    // Normalize the search username (remove discriminator if present)
    const searchUsername = username.toLowerCase().split('#')[0];
    
    // Search for the user by username (case-insensitive)
    const foundMember = members.find(member => {
      const memberUsername = member.user.username.toLowerCase();
      const memberGlobalName = member.user.global_name?.toLowerCase();
      return memberUsername === searchUsername || memberGlobalName === searchUsername;
    });
    
    if (!foundMember) {
      return res.status(404).json({ error: 'User not found in the server. Please make sure you entered the correct username.' });
    }
    
    res.status(200).json({ 
      success: true, 
      userId: foundMember.user.id,
      username: foundMember.user.username,
      discriminator: foundMember.user.discriminator,
      globalName: foundMember.user.global_name
    });
    
  } catch (err) {
    console.error('Discord user search error:', err);
    res.status(500).json({ error: 'Failed to search for Discord user', details: err.message });
  }
});
