import { createApp } from 'vue';
import { createPinia } from 'pinia';
import PrimeVue from 'primevue/config';
import Aura from '@primevue/themes/aura';
import ToastService from 'primevue/toastservice';
import ConfirmationService from 'primevue/confirmationservice';
import 'primeicons/primeicons.css';

import App from './App.vue';
import { router } from './router';
import { safeHtml } from './directives/safeHtml';
import './style.css';

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      darkModeSelector: '.dark',
    },
  },
});
app.use(ToastService);
app.use(ConfirmationService);

app.directive('safe-html', safeHtml);

// Global error handler — logs uncaught render/lifecycle/watcher errors so they
// surface in dev tools and any error-tracking service. Avoids silent failures
// when a component throws outside an explicit try/catch.
app.config.errorHandler = (err, _instance, info) => {
  // eslint-disable-next-line no-console
  console.error('[vue:errorHandler]', info, err);
};

app.mount('#app');
