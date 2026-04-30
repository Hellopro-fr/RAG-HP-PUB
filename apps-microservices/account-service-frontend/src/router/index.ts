import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/signin' },
    { path: '/signin', component: () => import('../views/Auth/Signin.vue') },
    { path: '/consent', component: () => import('../views/Auth/Consent.vue') },
    { path: '/logout', component: () => import('../views/Auth/Logout.vue') },
    { path: '/error', component: () => import('../views/Auth/Error.vue') },
    { path: '/:pathMatch(.*)*', component: () => import('../views/Auth/Error.vue') },
  ],
})

export default router
