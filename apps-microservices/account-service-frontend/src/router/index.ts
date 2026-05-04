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
    { path: '/admin/services', name: 'services', component: () => import('@/views/AdminServicesView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Services' } },
    { path: '/admin/services/new', name: 'service-create', component: () => import('@/views/ServiceFormView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Nouveau service' } },
    { path: '/admin/services/:id/edit', name: 'service-edit', component: () => import('@/views/ServiceFormView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Modifier service' } },
    { path: '/admin/users', name: 'users', component: () => import('@/views/AdminUsersView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Utilisateurs' } },
    { path: '/admin/users/:email/sessions', name: 'user-sessions', component: () => import('@/views/UserSessionsView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Sessions utilisateur' } },
    { path: '/admin/audit', name: 'audit', component: () => import('@/views/AuditLogView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: "Journal d'audit" } },
    {
      path: '/',
      name: 'root',
      redirect: () => {
        const a = useAuthStore()
        return a.isAdmin ? '/admin/services' : '/me'
      },
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
