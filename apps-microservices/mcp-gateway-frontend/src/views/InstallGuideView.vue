<template>
  <div>
    <PageBreadcrumb page-title="Guide d'installation" />

    <div class="max-w-4xl">
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">
        Instructions pour installer et configurer un client MCP avec le gateway.
      </p>

      <!-- Command tabs -->
      <div class="flex flex-wrap gap-2 mb-6">
        <button
          v-for="cmd in commands"
          :key="cmd.id"
          class="px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
          :class="activeCommand === cmd.id
            ? 'border-brand-500 text-brand-600 bg-brand-50 dark:bg-brand-500/10 dark:text-brand-400 dark:border-brand-400'
            : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500'"
          @click="activeCommand = cmd.id"
        >
          {{ cmd.label }}
          <span class="text-xs text-gray-400 dark:text-gray-500">{{ cmd.sub }}</span>
        </button>
      </div>

      <!-- Command content -->
      <div
        v-for="cmd in commands"
        :key="cmd.id"
        v-show="activeCommand === cmd.id"
        class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs overflow-hidden"
      >
        <!-- Header -->
        <div class="px-6 py-4 border-b border-gray-100 dark:border-gray-800">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">
            {{ cmd.label }}
            <span class="text-sm font-normal text-gray-500 dark:text-gray-400">- {{ cmd.description }}</span>
          </h2>
          <p class="text-sm text-gray-600 dark:text-gray-400 mt-1" v-safe-html="cmd.intro" />
        </div>

        <div class="px-6 py-4">
          <!-- OS tabs -->
          <div class="flex gap-2 mb-4">
            <button
              v-for="os in osList"
              :key="os.id"
              class="px-3 py-1.5 text-xs font-medium rounded-md border transition-colors"
              :class="activeOS === os.id
                ? 'border-brand-500 text-brand-600 bg-brand-50 dark:bg-brand-500/10 dark:text-brand-400 dark:border-brand-400 font-semibold'
                : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500'"
              @click="activeOS = os.id"
            >
              {{ os.label }}
            </button>
          </div>

          <!-- OS-specific install instructions -->
          <div
            v-for="os in osList"
            :key="os.id"
            v-show="activeOS === os.id"
          >
            <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Installation sur {{ os.label }}
            </h3>
            <div class="space-y-3">
              <div v-for="(option, i) in cmd.install[os.id]" :key="i">
                <p class="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  <strong>{{ option.label }}</strong>
                </p>
                <p v-if="option.note" class="text-sm text-gray-500 dark:text-gray-500 mb-1" v-safe-html="option.note" />
                <CodeBlock v-if="option.code" :code="option.code" @copy="handleCopy" />
              </div>
            </div>
          </div>

          <!-- Verification -->
          <div class="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
            <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Verification
            </h3>
            <CodeBlock :code="cmd.verify" @copy="handleCopy" />
          </div>

          <!-- MCP config -->
          <div class="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
            <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Utilisation avec MCP Gateway
            </h3>
            <p class="text-sm text-gray-600 dark:text-gray-400 mb-2">
              Ajoutez cette configuration dans votre fichier
              <code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">.mcp.json</code> :
            </p>
            <CodeBlock :code="cmd.mcpConfig" @copy="handleCopy" />
            <div
              v-if="cmd.noteText"
              class="mt-3 rounded-lg p-3 text-sm"
              :class="cmd.noteClass"
            >
              <strong>{{ cmd.noteLabel }}</strong> <span v-safe-html="cmd.noteText" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import CodeBlock from '@/components/shared/CodeBlock.vue'
import { useClipboard } from '@/composables/useClipboard'

const clipboard = useClipboard()
const activeCommand = ref('npx')
const activeOS = ref('windows')

function handleCopy(code: string) {
  clipboard.copy(code, 'Commande')
}

const osList = [
  { id: 'windows', label: 'Windows' },
  { id: 'linux', label: 'Linux' },
  { id: 'macos', label: 'macOS' },
]

interface InstallOption {
  label: string
  note?: string
  code?: string
}

interface CommandInfo {
  id: string
  label: string
  sub: string
  description: string
  intro: string
  install: Record<string, InstallOption[]>
  verify: string
  mcpConfig: string
  noteLabel: string
  noteText: string
  noteClass: string
}

const commands: CommandInfo[] = [
  {
    id: 'npx',
    label: 'npx',
    sub: '(Node.js)',
    description: 'Node.js Package Executor',
    intro: '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">npx</code> est inclus avec npm (Node.js). Il permet d\'executer des paquets npm sans installation globale. C\'est la commande par defaut et la plus courante pour les clients MCP.',
    install: {
      windows: [
        { label: 'Option 1 : Via winget (recommande)', code: 'winget install OpenJS.NodeJS.LTS' },
        { label: 'Option 2 : Via Chocolatey', code: 'choco install nodejs-lts' },
        { label: 'Option 3 : Installeur officiel', note: 'Telechargez le <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">.msi</code> depuis <a href="https://nodejs.org" target="_blank" class="text-brand-500 underline hover:text-brand-600">nodejs.org</a>' },
      ],
      linux: [
        { label: 'Option 1 : Via NodeSource (recommande)', code: 'curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -\nsudo apt-get install -y nodejs' },
        { label: 'Option 2 : Via nvm (Node Version Manager)', code: 'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash\nsource ~/.bashrc\nnvm install --lts' },
        { label: 'Option 3 : Via Snap', code: 'sudo snap install node --classic' },
      ],
      macos: [
        { label: 'Option 1 : Via Homebrew (recommande)', code: 'brew install node' },
        { label: 'Option 2 : Via nvm', code: 'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash\nsource ~/.zshrc\nnvm install --lts' },
        { label: 'Option 3 : Installeur officiel', note: 'Telechargez le <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">.pkg</code> depuis <a href="https://nodejs.org" target="_blank" class="text-brand-500 underline hover:text-brand-600">nodejs.org</a>' },
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
    sub: '(Bun)',
    description: 'Bun Package Executor',
    intro: '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">bunx</code> est l\'equivalent de npx pour le runtime <a href="https://bun.sh" target="_blank" class="text-brand-500 underline">Bun</a>. Plus rapide que npx, il est compatible avec les paquets npm.',
    install: {
      windows: [
        { label: 'Via PowerShell (recommande)', code: 'irm bun.sh/install.ps1 | iex' },
        { label: 'Via npm', code: 'npm install -g bun' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', code: 'curl -fsSL https://bun.sh/install | bash' },
        { label: 'Via npm', code: 'npm install -g bun' },
      ],
      macos: [
        { label: 'Via Homebrew (recommande)', code: 'brew install oven-sh/bun/bun' },
        { label: 'Via script', code: 'curl -fsSL https://bun.sh/install | bash' },
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
    sub: '(Deno)',
    description: 'Deno Runtime',
    intro: '<a href="https://deno.com" target="_blank" class="text-brand-500 underline">Deno</a> est un runtime JavaScript/TypeScript securise par defaut, avec support natif des paquets npm via le prefixe <code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">npm:</code>.',
    install: {
      windows: [
        { label: 'Via PowerShell (recommande)', code: 'irm https://deno.land/install.ps1 | iex' },
        { label: 'Via winget', code: 'winget install DenoLand.Deno' },
        { label: 'Via Chocolatey', code: 'choco install deno' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', code: 'curl -fsSL https://deno.land/install.sh | sh' },
        { label: 'Via Snap', code: 'sudo snap install deno' },
      ],
      macos: [
        { label: 'Via Homebrew (recommande)', code: 'brew install deno' },
        { label: 'Via script', code: 'curl -fsSL https://deno.land/install.sh | sh' },
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
    sub: '(Python / uv)',
    description: 'Python Package Executor (uv)',
    intro: '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">uvx</code> est l\'executeur de paquets de <a href="https://docs.astral.sh/uv/" target="_blank" class="text-brand-500 underline">uv</a>, le gestionnaire Python ultra-rapide d\'Astral. Il utilise le paquet <code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">mcp-proxy</code> pour se connecter au gateway.',
    install: {
      windows: [
        { label: 'Via PowerShell (recommande)', code: 'irm https://astral.sh/uv/install.ps1 | iex' },
        { label: 'Via winget', code: 'winget install astral-sh.uv' },
        { label: 'Via pip', code: 'pip install uv' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', code: 'curl -LsSf https://astral.sh/uv/install.sh | sh' },
        { label: 'Via pip', code: 'pip install uv' },
      ],
      macos: [
        { label: 'Via Homebrew (recommande)', code: 'brew install uv' },
        { label: 'Via script', code: 'curl -LsSf https://astral.sh/uv/install.sh | sh' },
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
    sub: '',
    description: 'Conteneur isole',
    intro: 'Execute le client MCP dans un conteneur Docker isole. Aucune dependance locale (Node.js, Python, etc.) n\'est requise — seul Docker doit etre installe.',
    install: {
      windows: [
        { label: 'Docker Desktop (recommande)', note: 'Telechargez depuis <a href="https://docs.docker.com/desktop/install/windows-install/" target="_blank" class="text-brand-500 underline">docker.com</a>. Prerequis : WSL 2 active.' },
        { label: 'Via winget', code: 'winget install Docker.DockerDesktop' },
      ],
      linux: [
        { label: 'Via script officiel (recommande)', code: 'curl -fsSL https://get.docker.com | sh\nsudo usermod -aG docker $USER\nnewgrp docker' },
        { label: 'Via apt (Ubuntu/Debian)', code: 'sudo apt-get update\nsudo apt-get install -y docker.io\nsudo systemctl enable --now docker' },
      ],
      macos: [
        { label: 'Docker Desktop (recommande)', note: 'Telechargez depuis <a href="https://docs.docker.com/desktop/install/mac-install/" target="_blank" class="text-brand-500 underline">docker.com</a>' },
        { label: 'Via Homebrew', code: 'brew install --cask docker' },
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
</script>
