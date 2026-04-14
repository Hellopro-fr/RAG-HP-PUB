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
      redirect: '/tokens'
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
      path: '/docs-admin',
      name: 'docs-admin',
      component: () => import('@/views/DocsAdminView.vue'),
      meta: { requiresAuth: true, title: 'Documentation', minRole: 'admin' }
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
      component: () => import('@/views/InstallGuideView.vue'),
      meta: { requiresAuth: true, title: "Guide d'installation" }
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
