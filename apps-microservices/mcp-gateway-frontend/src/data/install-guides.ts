export interface InstallOption {
  label: string
  note?: string
  code?: string
  noNumber?: boolean
}

export interface CommandInfo {
  id: string
  label: string
  sub: string
  description: string
  intro: string
  icon: string
  color: string
  install: Record<string, InstallOption[]>
  verify: string
  mcpConfig: string
  noteLabel: string
  noteText: string
  noteClass: string
}

// Terminal opening instructions per OS — prepended to every command's install list.
const terminalStep: Record<string, InstallOption> = {
  windows: {
    label: 'Ouvrir un terminal',
    note: 'Appuyez sur <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Win + R</kbd>, tapez <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">powershell</code> puis <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Entree</kbd>. Vous pouvez aussi chercher « PowerShell » ou « Terminal » dans le menu Demarrer.',
    noNumber: true,
  },
  linux: {
    label: 'Ouvrir un terminal',
    note: 'Appuyez sur <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Ctrl + Alt + T</kbd> (Ubuntu/Debian) ou cherchez « Terminal » dans le lanceur d\'applications.',
    noNumber: true,
  },
  macos: {
    label: 'Ouvrir un terminal',
    note: 'Appuyez sur <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Cmd + Espace</kbd>, tapez <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">Terminal</code> puis <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Entree</kbd>. Vous le trouverez aussi dans Applications > Utilitaires.',
    noNumber: true,
  },
}

export const commands: CommandInfo[] = [
  {
    id: 'npx',
    label: 'npx',
    sub: 'Node.js',
    description: 'Node.js Package Executor',
    intro: '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">npx</code> est inclus avec npm (Node.js). Il permet d\'executer des paquets npm sans installation globale. C\'est la commande par defaut et la plus courante pour les clients MCP.',
    icon: 'pi-box',
    color: 'text-green-600 bg-green-50 dark:bg-green-900/20 dark:text-green-400',
    install: {
      windows: [
        { label: 'Option 1 : Via winget (recommande)', note: 'Gestionnaire de paquets integre a Windows. Collez la commande dans le terminal et appuyez sur Entree. L\'installation demarre automatiquement.', code: 'winget install OpenJS.NodeJS.LTS' },
        { label: 'Option 2 : Via Chocolatey', note: 'Gestionnaire de paquets tiers pour Windows. Necessite que <a href="https://chocolatey.org/install" target="_blank" class="text-brand-500 underline">Chocolatey</a> soit deja installe. Collez la commande et validez.', code: 'choco install nodejs-lts' },
        { label: 'Option 3 : Installeur officiel', note: 'Telechargez le <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">.msi</code> depuis <a href="https://nodejs.org" target="_blank" class="text-brand-500 underline hover:text-brand-600">nodejs.org</a>, puis lancez l\'installeur et suivez les etapes. Redemarrez le terminal apres l\'installation.' },
      ],
      linux: [
        { label: 'Option 1 : Via NodeSource (recommande)', note: 'Ajoute le depot officiel NodeSource puis installe Node.js. Collez les deux lignes dans le terminal — la premiere configure le depot, la seconde installe le paquet.', code: 'curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -\nsudo apt-get install -y nodejs' },
        { label: 'Option 2 : Via nvm (Node Version Manager)', note: 'Installe nvm qui permet de gerer plusieurs versions de Node.js. Executez les trois commandes une par une : installation de nvm, rechargement du shell, puis installation de Node.js LTS.', code: 'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash\nsource ~/.bashrc\nnvm install --lts' },
        { label: 'Option 3 : Via Snap', note: 'Utilise le gestionnaire de paquets Snap (pre-installe sur Ubuntu). Une seule commande a coller.', code: 'sudo snap install node --classic' },
      ],
      macos: [
        { label: 'Option 1 : Via Homebrew (recommande)', note: 'Utilise le gestionnaire de paquets <a href="https://brew.sh" target="_blank" class="text-brand-500 underline">Homebrew</a>. Si Homebrew n\'est pas installe, suivez les instructions sur brew.sh. Collez la commande et attendez la fin de l\'installation.', code: 'brew install node' },
        { label: 'Option 2 : Via nvm', note: 'Installe nvm pour gerer les versions de Node.js. Executez les trois commandes dans l\'ordre : installation, rechargement du shell, puis installation de Node.js.', code: 'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash\nsource ~/.zshrc\nnvm install --lts' },
        { label: 'Option 3 : Installeur officiel', note: 'Telechargez le <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">.pkg</code> depuis <a href="https://nodejs.org" target="_blank" class="text-brand-500 underline hover:text-brand-600">nodejs.org</a>, lancez-le et suivez les etapes. Redemarrez le terminal apres l\'installation.' },
      ],
    },
    verify: 'node --version   # v18+ requis\nnpx --version',
    mcpConfig: `{
  "mcpServers": {
    "hellopro-gateway": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://<gateway-url>/mcp",
        "--header",
        "X-MCP-Scope-Token: \${MCP_SCOPE_TOKEN}"
      ],
      "env": {
        "MCP_SCOPE_TOKEN": "<votre-token>"
      }
    }
  }
}`,
    noteLabel: 'Note :',
    noteText: 'Le flag <code class="bg-amber-100 dark:bg-amber-500/20 px-1 rounded text-xs">-y</code> accepte automatiquement l\'installation du paquet <code class="bg-amber-100 dark:bg-amber-500/20 px-1 rounded text-xs">mcp-remote</code> sans confirmation. Ajoutez <code class="bg-amber-100 dark:bg-amber-500/20 px-1 rounded text-xs">--allow-http</code> si votre gateway utilise HTTP (non-HTTPS).',
    noteClass: 'bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-300',
  },
  {
    id: 'bunx',
    label: 'bunx',
    sub: 'Bun',
    description: 'Bun Package Executor',
    intro: '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">bunx</code> est l\'equivalent de npx pour le runtime <a href="https://bun.sh" target="_blank" class="text-brand-500 underline">Bun</a>. Plus rapide que npx, il est compatible avec les paquets npm.',
    icon: 'pi-bolt',
    color: 'text-orange-600 bg-orange-50 dark:bg-orange-900/20 dark:text-orange-400',
    install: {
      windows: [
        { label: 'Via PowerShell (recommande)', note: 'Telecharge et execute le script d\'installation officiel de Bun. Collez la commande dans PowerShell et attendez la fin du telechargement.', code: 'irm bun.sh/install.ps1 | iex' },
        { label: 'Via npm', note: 'Si Node.js est deja installe, vous pouvez installer Bun via npm en global. Collez la commande et validez.', code: 'npm install -g bun' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', note: 'Telecharge et execute le script d\'installation officiel. La commande installe Bun dans votre repertoire utilisateur.', code: 'curl -fsSL https://bun.sh/install | bash' },
        { label: 'Via npm', note: 'Alternative si Node.js est deja present. Installe Bun globalement via npm.', code: 'npm install -g bun' },
      ],
      macos: [
        { label: 'Via Homebrew (recommande)', note: 'Installe Bun via le tap officiel Homebrew. Une seule commande a coller dans le terminal.', code: 'brew install oven-sh/bun/bun' },
        { label: 'Via script', note: 'Telecharge et execute le script d\'installation officiel de Bun.', code: 'curl -fsSL https://bun.sh/install | bash' },
      ],
    },
    verify: 'bun --version\nbunx --version',
    mcpConfig: `{
  "mcpServers": {
    "hellopro-gateway": {
      "command": "bunx",
      "args": [
        "mcp-remote",
        "https://<gateway-url>/mcp",
        "--header",
        "X-MCP-Scope-Token: \${MCP_SCOPE_TOKEN}"
      ],
      "env": {
        "MCP_SCOPE_TOKEN": "<votre-token>"
      }
    }
  }
}`,
    noteLabel: 'Avantage :',
    noteText: 'bunx ne necessite pas le flag <code class="bg-emerald-100 dark:bg-emerald-500/20 px-1 rounded text-xs">-y</code> — il installe automatiquement les paquets manquants.',
    noteClass: 'bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-800 dark:text-emerald-300',
  },
  {
    id: 'deno',
    label: 'deno',
    sub: 'Deno',
    description: 'Deno Runtime',
    intro: '<a href="https://deno.com" target="_blank" class="text-brand-500 underline">Deno</a> est un runtime JavaScript/TypeScript securise par defaut, avec support natif des paquets npm via le prefixe <code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">npm:</code>.',
    icon: 'pi-shield',
    color: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20 dark:text-blue-400',
    install: {
      windows: [
        { label: 'Via PowerShell (recommande)', note: 'Telecharge et execute le script d\'installation officiel de Deno. Collez la commande dans PowerShell et validez.', code: 'irm https://deno.land/install.ps1 | iex' },
        { label: 'Via winget', note: 'Utilise le gestionnaire de paquets integre a Windows. Collez et validez.', code: 'winget install DenoLand.Deno' },
        { label: 'Via Chocolatey', note: 'Necessite que Chocolatey soit installe. Collez la commande et validez.', code: 'choco install deno' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', note: 'Telecharge et installe Deno dans votre repertoire utilisateur. Ajoutez ensuite le chemin a votre PATH si ce n\'est pas fait automatiquement.', code: 'curl -fsSL https://deno.land/install.sh | sh' },
        { label: 'Via Snap', note: 'Installe Deno via le gestionnaire Snap. Disponible sur Ubuntu et les distributions compatibles.', code: 'sudo snap install deno' },
      ],
      macos: [
        { label: 'Via Homebrew (recommande)', note: 'Installe Deno via Homebrew. Une seule commande a coller dans le terminal.', code: 'brew install deno' },
        { label: 'Via script', note: 'Telecharge et installe Deno via le script officiel.', code: 'curl -fsSL https://deno.land/install.sh | sh' },
      ],
    },
    verify: 'deno --version',
    mcpConfig: `{
  "mcpServers": {
    "hellopro-gateway": {
      "command": "deno",
      "args": [
        "run",
        "--allow-all",
        "npm:mcp-remote",
        "https://<gateway-url>/mcp",
        "--header",
        "X-MCP-Scope-Token: \${MCP_SCOPE_TOKEN}"
      ],
      "env": {
        "MCP_SCOPE_TOKEN": "<votre-token>"
      }
    }
  }
}`,
    noteLabel: 'Note :',
    noteText: 'Le flag <code class="bg-blue-100 dark:bg-blue-500/20 px-1 rounded text-xs">--allow-all</code> accorde toutes les permissions au script. Pour plus de securite, utilisez <code class="bg-blue-100 dark:bg-blue-500/20 px-1 rounded text-xs">--allow-net --allow-read --allow-env</code>.',
    noteClass: 'bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/30 text-blue-800 dark:text-blue-300',
  },
  {
    id: 'uvx',
    label: 'uvx',
    sub: 'Python / uv',
    description: 'Python Package Executor (uv)',
    intro: '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">uvx</code> est l\'executeur de paquets de <a href="https://docs.astral.sh/uv/" target="_blank" class="text-brand-500 underline">uv</a>, le gestionnaire Python ultra-rapide d\'Astral. Il utilise le paquet <code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">mcp-proxy</code> pour se connecter au gateway.',
    icon: 'pi-code',
    color: 'text-purple-600 bg-purple-50 dark:bg-purple-900/20 dark:text-purple-400',
    install: {
      windows: [
        { label: 'Via PowerShell (recommande)', note: 'Telecharge et execute le script d\'installation officiel d\'uv. Collez la commande dans PowerShell et validez. uv et uvx seront disponibles immediatement.', code: 'irm https://astral.sh/uv/install.ps1 | iex' },
        { label: 'Via winget', note: 'Utilise le gestionnaire de paquets integre a Windows pour installer uv.', code: 'winget install astral-sh.uv' },
        { label: 'Via pip', note: 'Si Python est deja installe, vous pouvez installer uv via pip. Attention : Python doit etre dans votre PATH.', code: 'pip install uv' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', note: 'Telecharge et installe uv dans votre repertoire utilisateur. Le script ajoute automatiquement uv a votre PATH.', code: 'curl -LsSf https://astral.sh/uv/install.sh | sh' },
        { label: 'Via pip', note: 'Alternative si Python et pip sont deja installes sur votre systeme.', code: 'pip install uv' },
      ],
      macos: [
        { label: 'Via Homebrew (recommande)', note: 'Installe uv via Homebrew. Une seule commande — uv et uvx sont immediatement disponibles.', code: 'brew install uv' },
        { label: 'Via script', note: 'Telecharge et installe uv via le script officiel d\'Astral.', code: 'curl -LsSf https://astral.sh/uv/install.sh | sh' },
      ],
    },
    verify: 'uv --version\nuvx --version',
    mcpConfig: `{
  "mcpServers": {
    "hellopro-gateway": {
      "command": "uvx",
      "args": [
        "mcp-proxy",
        "https://<gateway-url>/mcp",
        "--header",
        "X-MCP-Scope-Token: \${MCP_SCOPE_TOKEN}"
      ],
      "env": {
        "MCP_SCOPE_TOKEN": "<votre-token>"
      }
    }
  }
}`,
    noteLabel: 'Note :',
    noteText: 'uvx utilise le paquet Python <code class="bg-purple-100 dark:bg-purple-500/20 px-1 rounded text-xs">mcp-proxy</code> (et non <code class="bg-purple-100 dark:bg-purple-500/20 px-1 rounded text-xs">mcp-remote</code> qui est un paquet npm). L\'API est compatible.',
    noteClass: 'bg-purple-50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/30 text-purple-800 dark:text-purple-300',
  },
  {
    id: 'docker',
    label: 'docker',
    sub: 'Docker',
    description: 'Conteneur isole',
    intro: 'Execute le client MCP dans un conteneur Docker isole. Aucune dependance locale (Node.js, Python, etc.) n\'est requise — seul Docker doit etre installe.',
    icon: 'pi-server',
    color: 'text-cyan-600 bg-cyan-50 dark:bg-cyan-900/20 dark:text-cyan-400',
    install: {
      windows: [
        { label: 'Docker Desktop (recommande)', note: 'Telechargez l\'installeur depuis <a href="https://docs.docker.com/desktop/install/windows-install/" target="_blank" class="text-brand-500 underline">docker.com</a>. Lancez le fichier .exe et suivez les etapes. Prerequis : WSL 2 doit etre active (Docker Desktop vous guidera si ce n\'est pas le cas). Redemarrez apres l\'installation.' },
        { label: 'Via winget', note: 'Installe Docker Desktop via le gestionnaire de paquets Windows. Collez la commande et validez. Un redemarrage peut etre necessaire.', code: 'winget install Docker.DockerDesktop' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', note: 'Le script detecte votre distribution et installe Docker Engine. Les deux commandes suivantes ajoutent votre utilisateur au groupe docker (pour eviter d\'utiliser sudo a chaque fois).', code: 'curl -fsSL https://get.docker.com | sh\nsudo usermod -aG docker $USER\nnewgrp docker' },
        { label: 'Via apt (Ubuntu/Debian)', note: 'Installation manuelle via le gestionnaire de paquets apt. Met a jour la liste des paquets, installe Docker, puis active le service.', code: 'sudo apt-get update\nsudo apt-get install -y docker.io\nsudo systemctl enable --now docker' },
      ],
      macos: [
        { label: 'Docker Desktop (recommande)', note: 'Telechargez l\'installeur depuis <a href="https://docs.docker.com/desktop/install/mac-install/" target="_blank" class="text-brand-500 underline">docker.com</a>. Ouvrez le fichier .dmg et faites glisser Docker dans Applications. Lancez Docker Desktop depuis le Launchpad.' },
        { label: 'Via Homebrew', note: 'Installe Docker Desktop via Homebrew en tant qu\'application (cask). Lancez ensuite Docker Desktop depuis le Launchpad.', code: 'brew install --cask docker' },
      ],
    },
    verify: 'docker --version\ndocker run hello-world',
    mcpConfig: `{
  "mcpServers": {
    "hellopro-gateway": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "MCP_SCOPE_TOKEN",
        "ghcr.io/anthropics/mcp-remote",
        "https://<gateway-url>/mcp",
        "--header",
        "X-MCP-Scope-Token: \${MCP_SCOPE_TOKEN}"
      ],
      "env": {
        "MCP_SCOPE_TOKEN": "<votre-token>"
      }
    }
  }
}`,
    noteLabel: 'Flags importants :',
    noteText: '<code class="bg-blue-100 dark:bg-blue-500/20 px-1 rounded text-xs">-i</code> : mode interactif (requis pour stdin/stdout MCP). <code class="bg-blue-100 dark:bg-blue-500/20 px-1 rounded text-xs">--rm</code> : supprime le conteneur apres l\'arret.',
    noteClass: 'bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/30 text-blue-800 dark:text-blue-300',
  },
]

export function getCommandById(id: string): CommandInfo | undefined {
  const cmd = commands.find(c => c.id === id)
  if (!cmd) return undefined
  // Prepend terminal opening step to each OS install list
  const install: Record<string, InstallOption[]> = {}
  for (const os of Object.keys(cmd.install)) {
    install[os] = [terminalStep[os]!, ...cmd.install[os]!]
  }
  return { ...cmd, install }
}

export const osList = [
  { id: 'windows', label: 'Windows', icon: 'pi-microsoft' },
  { id: 'linux', label: 'Linux', icon: 'pi-server' },
  { id: 'macos', label: 'macOS', icon: 'pi-apple' },
]

// ── MCP Client Configurations ──────────────────────────────────────

export interface ConfigCard {
  id: string
  label: string
  description: string
  icon: string
  color: string
}

export const mcpConfigs: ConfigCard[] = [
  {
    id: 'claude-code',
    label: 'Claude Code',
    description: 'Configuration via le CLI Claude Code avec la commande claude mcp add.',
    icon: 'pi-code',
    color: 'text-gray-900 bg-gray-100 dark:bg-gray-700 dark:text-white',
  },
  {
    id: 'claude-desktop',
    label: 'Claude Desktop',
    description: 'Configuration via le fichier claude_desktop_config.json de l\'application Claude Desktop.',
    icon: 'pi-desktop',
    color: 'text-brand-600 bg-brand-50 dark:bg-brand-900/20 dark:text-brand-400',
  },
  {
    id: 'claude-oauth2',
    label: 'Claude via OAuth2',
    description: 'Connexion securisee via Client ID, Client Secret et autorisation OAuth2.',
    icon: 'pi-lock',
    color: 'text-purple-600 bg-purple-50 dark:bg-purple-900/20 dark:text-purple-400',
  },
]

export function getConfigById(id: string): ConfigCard | undefined {
  return mcpConfigs.find(c => c.id === id)
}
