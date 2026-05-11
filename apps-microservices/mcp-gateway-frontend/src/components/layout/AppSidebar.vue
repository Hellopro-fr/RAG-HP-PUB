<template>
  <aside
    :class="[
      'fixed mt-16 flex flex-col lg:mt-0 top-0 px-5 left-0 bg-white dark:bg-gray-900 dark:border-gray-800 text-gray-900 h-screen transition-all duration-300 ease-in-out z-10 border-r border-gray-200',
      {
        'lg:w-[290px]': isExpanded || isMobileOpen || isHovered,
        'lg:w-[90px]': !isExpanded && !isHovered,
        'translate-x-0 w-[290px]': isMobileOpen,
        '-translate-x-full': !isMobileOpen,
        'lg:translate-x-0': true,
      },
    ]"
    @mouseenter="!isExpanded && (isHovered = true)"
    @mouseleave="isHovered = false"
  >
    <!-- Logo -->
    <div
      :class="[
        'py-8 flex',
        !isExpanded && !isHovered ? 'lg:justify-center' : 'justify-start',
      ]"
    >
      <router-link to="/" class="flex items-center gap-2">
        <img src="/images/servers/hp-logo.svg" alt="Hellopro" class="w-6 h-6" />
        <span
          v-if="isExpanded || isHovered || isMobileOpen"
          class="text-lg font-bold tracking-wide text-gray-900 dark:text-white"
        >
          MCP Gateway
        </span>
        <span
          v-else
          class="text-sm font-bold text-gray-900 dark:text-white"
        >
          MCP
        </span>
      </router-link>
    </div>

    <!-- Navigation -->
    <div class="flex flex-col overflow-y-auto duration-300 ease-linear no-scrollbar">
      <nav class="mb-6">
        <div class="flex flex-col gap-4">
          <div v-for="(menuGroup, groupIndex) in menuGroups" :key="groupIndex">
            <h2
              :class="[
                'mb-4 text-xs uppercase flex leading-[20px] text-gray-400',
                !isExpanded && !isHovered
                  ? 'lg:justify-center'
                  : 'justify-start',
              ]"
            >
              <template v-if="isExpanded || isHovered || isMobileOpen">
                {{ menuGroup.title }}
              </template>
              <i v-else class="pi pi-ellipsis-h text-xs" />
            </h2>
            <ul class="flex flex-col gap-4">
              <li v-for="(item, index) in menuGroup.items" :key="item.name">
                <!-- Submenu button -->
                <button
                  v-if="item.subItems"
                  @click="toggleSubmenu(groupIndex, index)"
                  :class="[
                    'menu-item group w-full',
                    {
                      'menu-item-active': isSubmenuOpen(groupIndex, index),
                      'menu-item-inactive': !isSubmenuOpen(groupIndex, index),
                    },
                    !isExpanded && !isHovered
                      ? 'lg:justify-center'
                      : 'lg:justify-start',
                  ]"
                >
                  <span
                    :class="[
                      isSubmenuOpen(groupIndex, index)
                        ? 'menu-item-icon-active'
                        : 'menu-item-icon-inactive',
                    ]"
                  >
                    <i :class="[item.icon, 'text-base']" />
                  </span>
                  <span
                    v-if="isExpanded || isHovered || isMobileOpen"
                    class="menu-item-text"
                  >
                    {{ item.name }}
                  </span>
                  <i
                    v-if="isExpanded || isHovered || isMobileOpen"
                    :class="[
                      'pi pi-chevron-down ml-auto w-5 h-5 transition-transform duration-200',
                      {
                        'rotate-180 text-brand-500': isSubmenuOpen(groupIndex, index),
                      },
                    ]"
                  />
                </button>

                <!-- External link (new tab) -->
                <a
                  v-else-if="item.path && item.newTab"
                  :href="item.path"
                  target="_blank"
                  rel="noopener noreferrer"
                  :class="[
                    'menu-item group menu-item-inactive',
                    !isExpanded && !isHovered
                      ? 'lg:justify-center'
                      : 'lg:justify-start',
                  ]"
                >
                  <span class="menu-item-icon-inactive">
                    <i :class="[item.icon, 'text-base']" />
                  </span>
                  <span
                    v-if="isExpanded || isHovered || isMobileOpen"
                    class="menu-item-text"
                  >
                    {{ item.name }}
                  </span>
                  <i
                    v-if="isExpanded || isHovered || isMobileOpen"
                    class="pi pi-external-link ml-auto text-[10px] opacity-60"
                  />
                </a>

                <!-- Direct link (no submenu) -->
                <router-link
                  v-else-if="item.path"
                  :to="item.path"
                  :class="[
                    'menu-item group',
                    {
                      'menu-item-active': isActive(item.path),
                      'menu-item-inactive': !isActive(item.path),
                    },
                    !isExpanded && !isHovered
                      ? 'lg:justify-center'
                      : 'lg:justify-start',
                  ]"
                >
                  <span
                    :class="[
                      isActive(item.path)
                        ? 'menu-item-icon-active'
                        : 'menu-item-icon-inactive',
                    ]"
                  >
                    <i :class="[item.icon, 'text-base']" />
                  </span>
                  <span
                    v-if="isExpanded || isHovered || isMobileOpen"
                    class="menu-item-text"
                  >
                    {{ item.name }}
                  </span>
                </router-link>

                <!-- Submenu items -->
                <transition
                  @enter="startTransition"
                  @after-enter="endTransition"
                  @before-leave="startTransition"
                  @after-leave="endTransition"
                >
                  <div
                    v-show="
                      isSubmenuOpen(groupIndex, index) &&
                      (isExpanded || isHovered || isMobileOpen)
                    "
                  >
                    <ul class="mt-2 space-y-1 ml-9">
                      <li v-for="subItem in item.subItems" :key="subItem.name">
                        <router-link
                          :to="subItem.path"
                          :class="[
                            'menu-dropdown-item',
                            {
                              'menu-dropdown-item-active': isActive(subItem.path),
                              'menu-dropdown-item-inactive': !isActive(subItem.path),
                            },
                          ]"
                        >
                          {{ subItem.name }}
                        </router-link>
                      </li>
                    </ul>
                  </div>
                </transition>
              </li>
            </ul>
          </div>
        </div>
      </nav>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useSidebar } from '@/composables/useSidebar';
import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const { isExpanded, isMobileOpen, isHovered, openSubmenu } = useSidebar();
const authStore = useAuthStore();

interface SubItem {
  name: string;
  path: string;
}

interface MenuItem {
  icon: string;
  name: string;
  path?: string;
  subItems?: SubItem[];
  newTab?: boolean;
}

interface MenuGroup {
  title: string;
  items: MenuItem[];
}

const menuGroups = computed<MenuGroup[]>(() => {
  const groups: MenuGroup[] = []

  // Gestion group — Serveurs only for read-only+, Config MCP always
  const gestionItems: MenuItem[] = []
  if (authStore.isAdmin) {
    gestionItems.push({
      icon: 'pi pi-objects-column',
      name: 'Tableau de bord',
      path: '/dashboard',
    })
  }
  if (authStore.hasRole('read-only')) {
    gestionItems.push({
      icon: 'pi pi-server',
      name: 'Serveurs',
      path: '/servers',
    })
  }
  gestionItems.push({
    icon: 'pi pi-database',
    name: 'Tables BDD',
    path: '/bdd-tables',
  })
  if (authStore.isAdmin) {
    gestionItems.push({
      icon: 'pi pi-book',
      name: 'Documentation',
      path: '/docs-admin',
    })
    gestionItems.push({
      icon: 'pi pi-map',
      name: "Guides d'installation",
      path: '/install-guides-admin',
    })
    gestionItems.push({
      icon: 'pi pi-clone',
      name: 'Templates',
      path: '/admin/templates',
    })
  }
  gestionItems.push({
    icon: 'pi pi-key',
    name: 'Config MCP',
    path: '/tokens',
  })
  gestionItems.push({
    icon: 'pi pi-comment',
    name: 'Instructions LLM',
    path: '/llm-instructions',
  })
  if (gestionItems.length > 0) {
    groups.push({ title: 'Gestion', items: gestionItems })
  }

  // Securite group — OAuth2 always; Serveur Autorisation admin-only
  const securiteItems: MenuItem[] = [
    {
      icon: 'pi pi-shield',
      name: 'OAuth2',
      path: '/oauth2',
    },
  ]
  if (authStore.isAdmin) {
    securiteItems.push({
      icon: 'pi pi-user-plus',
      name: 'Serveur Autorisation',
      path: '/server-authorizations',
    })
  }
  groups.push({
    title: 'Securite',
    items: securiteItems,
  })

  // Administration group — only for admins
  if (authStore.isAdmin) {
    groups.push({
      title: 'Administration',
      items: [
        {
          icon: 'pi pi-users',
          name: 'Utilisateurs',
          path: '/users',
        },
        {
          icon: 'pi pi-list',
          name: "Journal d'audit",
          path: '/audit-logs',
        },
        {
          icon: 'pi pi-cog',
          name: 'Paramètres',
          path: '/settings',
        },
      ],
    })
  }

  // Aide group — always
  groups.push({
    title: 'Aide',
    items: [
      {
        icon: 'pi pi-book',
        name: "Guide d'installation",
        path: '/install-guide',
        newTab: true,
      },
      {
        icon: 'pi pi-file',
        name: 'Documentation des outils',
        path: '/docs',
        newTab: true,
      },
    ],
  })

  return groups
})

const isActive = (path: string): boolean => route.path.startsWith(path);

const toggleSubmenu = (groupIndex: number, itemIndex: number): void => {
  const key = `${groupIndex}-${itemIndex}`;
  openSubmenu.value = openSubmenu.value === key ? null : key;
};

const isAnySubmenuRouteActive = computed(() => {
  return menuGroups.value.some((group) =>
    group.items.some(
      (item) =>
        item.subItems && item.subItems.some((subItem) => isActive(subItem.path))
    )
  );
});

const isSubmenuOpen = (groupIndex: number, itemIndex: number): boolean => {
  const key = `${groupIndex}-${itemIndex}`;
  const item = menuGroups.value[groupIndex]?.items[itemIndex];
  return (
    openSubmenu.value === key ||
    (isAnySubmenuRouteActive.value &&
      item?.subItems?.some((subItem) =>
        isActive(subItem.path)
      ) === true)
  );
};

const startTransition = (el: Element): void => {
  const htmlEl = el as HTMLElement;
  htmlEl.style.height = 'auto';
  const height = htmlEl.scrollHeight;
  htmlEl.style.height = '0px';
  htmlEl.offsetHeight; // force reflow
  htmlEl.style.height = height + 'px';
};

const endTransition = (el: Element): void => {
  const htmlEl = el as HTMLElement;
  htmlEl.style.height = '';
};
</script>
