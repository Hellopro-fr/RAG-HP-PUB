import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    title?: string
    minRole?: 'admin' | 'user'
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { left: 0, top: 0 }
  },
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { requiresAuth: false, title: 'Connexion' } },
    { path: '/me', name: 'me', component: () => import('@/views/MeView.vue'), meta: { requiresAuth: true, title: 'Profil' } },
    // Services + parameters: open to any authenticated user (full access)
    { path: '/admin/services', name: 'services', component: () => import('@/views/AdminServicesView.vue'), meta: { requiresAuth: true, title: 'Services' } },
    { path: '/admin/services/new', name: 'service-create', component: () => import('@/views/ServiceFormView.vue'), meta: { requiresAuth: true, title: 'Nouveau service' } },
    { path: '/admin/services/:id/edit', name: 'service-edit', component: () => import('@/views/ServiceFormView.vue'), meta: { requiresAuth: true, title: 'Modifier service' } },
    { path: '/admin/api',          name: 'api-list',   component: () => import('@/views/ApiCatalogListView.vue'),   meta: { requiresAuth: true, title: 'API' } },
    { path: '/admin/api/new',      name: 'api-create', component: () => import('@/views/ApiCatalogFormView.vue'),   meta: { requiresAuth: true, title: 'Nouvelle API' } },
    { path: '/admin/api/:id',      name: 'api-detail', component: () => import('@/views/ApiCatalogDetailView.vue'), meta: { requiresAuth: true, title: 'Détail API' } },
    { path: '/admin/api/:id/edit', name: 'api-edit',   component: () => import('@/views/ApiCatalogFormView.vue'),   meta: { requiresAuth: true, title: 'Modifier API' } },
    { path: '/admin/parameters', name: 'parameters', component: () => import('@/views/ParametersView.vue'), meta: { requiresAuth: true, title: 'Paramètres' } },
    // Users + sessions + audit: admin-only
    { path: '/admin/users', name: 'users', component: () => import('@/views/AdminUsersView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Utilisateurs' } },
    { path: '/admin/users/:email/sessions', name: 'user-sessions', component: () => import('@/views/UserSessionsView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Sessions utilisateur' } },
    { path: '/admin/audit', name: 'audit', component: () => import('@/views/AuditLogView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: "Journal d'audit" } },
    {
      path: '/',
      name: 'root',
      redirect: () => '/admin/services',
    },
    { path: '/:pathMatch(.*)*', redirect: '/login' },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.requiresAuth === false) return true

  const a = useAuthStore()
  if (!a.isAuthenticated) {
    const ok = await a.checkSession()
    if (!ok) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta.minRole === 'admin' && !a.isAdmin) {
    return { path: '/me' }
  }
  return true
})

export default router
