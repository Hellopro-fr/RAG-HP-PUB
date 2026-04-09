import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

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
      path: '/',
      redirect: '/servers'
    },
    {
      path: '/servers/new',
      name: 'server-create',
      component: () => import('@/views/ServerFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouveau serveur' }
    },
    {
      path: '/servers/:id/edit',
      name: 'server-edit',
      component: () => import('@/views/ServerFormView.vue'),
      meta: { requiresAuth: true, title: 'Modifier le serveur' }
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
      meta: { requiresAuth: true, title: 'Serveurs MCP' }
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

  return true
})

export { router }
