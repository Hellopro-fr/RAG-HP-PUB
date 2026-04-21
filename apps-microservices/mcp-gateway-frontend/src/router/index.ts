import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, type UserRole } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    title?: string
    minRole?: UserRole
    layout?: 'docs'
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/authorize',
      name: 'authorize',
      component: () => import('@/views/AuthorizeView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: () => import('@/views/PrivacyPolicyView.vue'),
      meta: { requiresAuth: false, title: 'Politique de confidentialité' }
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('@/views/AppHomepageView.vue'),
      meta: { requiresAuth: false, title: 'MCP Gateway' }
    },
    {
      path: '/docs',
      name: 'docs',
      component: () => import('@/views/DocsServersView.vue'),
      meta: { requiresAuth: false, layout: 'docs', title: 'Documentation' }
    },
    {
      path: '/docs/:serverSlug',
      name: 'docs-server',
      component: () => import('@/views/DocsServerDetailView.vue'),
      meta: { requiresAuth: false, layout: 'docs', title: 'Documentation serveur' }
    },
    {
      path: '/',
      name: 'home',
      redirect: () => {
        const authStore = useAuthStore()
        return authStore.isAdmin ? '/dashboard' : '/tokens'
      }
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresAuth: true, title: 'Tableau de bord', minRole: 'admin' }
    },
    {
      path: '/servers/new',
      name: 'server-create',
      component: () => import('@/views/ServerFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouveau serveur', minRole: 'admin' }
    },
    {
      path: '/servers/:id/edit',
      name: 'server-edit',
      component: () => import('@/views/ServerFormView.vue'),
      meta: { requiresAuth: true, title: 'Modifier le serveur', minRole: 'admin' }
    },
    {
      path: '/servers/:id/documentation',
      name: 'server-doc',
      component: () => import('@/views/ServerDocView.vue'),
      meta: { requiresAuth: true, title: 'Documentation serveur', minRole: 'admin' }
    },
    {
      path: '/tokens/new',
      name: 'token-create',
      component: () => import('@/views/TokenFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouveau jeton' }
    },
    {
      path: '/tokens/:id/edit',
      name: 'token-edit',
      component: () => import('@/views/TokenFormView.vue'),
      meta: { requiresAuth: true, title: 'Modifier le jeton' }
    },
    {
      path: '/oauth2/new',
      name: 'client-create',
      component: () => import('@/views/ClientFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouveau client' }
    },
    {
      path: '/oauth2/:id/edit',
      name: 'client-edit',
      component: () => import('@/views/ClientFormView.vue'),
      meta: { requiresAuth: true, title: 'Modifier le client' }
    },
    {
      path: '/servers',
      name: 'servers',
      component: () => import('@/views/ServersView.vue'),
      meta: { requiresAuth: true, title: 'Serveurs MCP', minRole: 'read-only' }
    },
    {
      path: '/servers/import-google',
      name: 'google-sheets-import',
      component: () => import('@/views/GoogleSheetsImportView.vue'),
      meta: { requiresAuth: true, title: 'Import Google Sheets', minRole: 'admin' }
    },
    {
      path: '/docs-admin',
      name: 'docs-admin',
      component: () => import('@/views/DocsAdminView.vue'),
      meta: { requiresAuth: true, title: 'Documentation', minRole: 'admin' }
    },
    {
      path: '/admin/templates',
      name: 'templates',
      component: () => import('@/views/TemplatesView.vue'),
      meta: { requiresAuth: true, title: 'Templates', minRole: 'admin' }
    },
    {
      path: '/admin/templates/:slug',
      name: 'template-detail',
      component: () => import('@/views/TemplateDetailView.vue'),
      meta: { requiresAuth: true, title: 'Template', minRole: 'admin' },
      props: true
    },
    {
      path: '/tokens',
      name: 'tokens',
      component: () => import('@/views/TokensView.vue'),
      meta: { requiresAuth: true, title: 'Configuration MCP' }
    },
    {
      path: '/oauth2',
      name: 'oauth2',
      component: () => import('@/views/OAuth2View.vue'),
      meta: { requiresAuth: true, title: 'Clients OAuth2' }
    },
    {
      path: '/install-guide',
      name: 'install-guide',
      component: () => import('@/views/InstallGuidesListView.vue'),
      meta: { requiresAuth: false, layout: 'docs', title: "Guide d'installation" }
    },
    {
      path: '/install-guide/config/:slug',
      name: 'install-guide-config',
      component: () => import('@/views/InstallConfigDetailView.vue'),
      meta: { requiresAuth: false, layout: 'docs', title: 'Configuration MCP' }
    },
    {
      path: '/install-guide/:slug',
      name: 'install-guide-detail',
      component: () => import('@/views/InstallGuideDetailView.vue'),
      meta: { requiresAuth: false, layout: 'docs', title: "Guide d'installation" }
    },
    {
      path: '/install-guides-admin',
      name: 'install-guides-admin',
      component: () => import('@/views/InstallGuidesAdminView.vue'),
      meta: { requiresAuth: true, title: "Guides d'installation", minRole: 'admin' }
    },
    {
      path: '/install-guides-admin/executors/new',
      name: 'executor-create',
      component: () => import('@/views/ExecutorFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouvel executeur', minRole: 'admin' }
    },
    {
      path: '/install-guides-admin/executors/:id/edit',
      name: 'executor-edit',
      component: () => import('@/views/ExecutorFormView.vue'),
      meta: { requiresAuth: true, title: 'Modifier executeur', minRole: 'admin' }
    },
    {
      path: '/install-guides-admin/configs/new',
      name: 'config-create',
      component: () => import('@/views/ConfigFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouvelle configuration', minRole: 'admin' }
    },
    {
      path: '/install-guides-admin/configs/:id/edit',
      name: 'config-edit',
      component: () => import('@/views/ConfigFormView.vue'),
      meta: { requiresAuth: true, title: 'Modifier configuration', minRole: 'admin' }
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('@/views/UsersView.vue'),
      meta: { requiresAuth: true, title: 'Utilisateurs', minRole: 'admin' }
    },
    {
      path: '/audit-logs',
      name: 'audit-logs',
      component: () => import('@/views/AuditLogView.vue'),
      meta: { requiresAuth: true, title: "Journal d'audit", minRole: 'admin' }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { requiresAuth: true, title: 'Paramètres', minRole: 'admin' }
    }
  ]
})

router.beforeEach(async (to) => {
  if (to.meta.requiresAuth === false) {
    return true
  }

  const authStore = useAuthStore()

  if (!authStore.isAuthenticated) {
    const valid = await authStore.checkSession()
    if (!valid) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  const minRole = to.meta.minRole
  if (minRole && !authStore.hasRole(minRole)) {
    return { path: '/tokens' }
  }

  return true
})

export { router }
