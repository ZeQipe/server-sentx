// Моковые данные для разработки
export const getMockMainPage = (timeout = 500) => {
  const mockMainPageData = {
    pagesAmount: 29,
    activePage: 1,
    data: [
      {
        uid: "c7d229bd-26c4-4757-9edb-cbe5f7765ca4",
        email: "da000shi@gmail.com",
        session: "New chat",
      },
      {
        uid: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        email: "user@example.com",
        session: "Previous chat",
      },
      {
        uid: "f9e8d7c6-b5a4-3210-9876-543210fedcba",
        email: "admin@test.com",
        session: "Support chat",
      },
    ],
  }

  return new Promise((res) => {
    setTimeout(() => {
      res(mockMainPageData)
    }, timeout)
  })
}

export const mockDateFilters = [
  { name: "All dates", value: 0, active: false },
  { name: "April 2025", value: "April 2025", active: false },
  { name: "April 2024", value: "April 2024", active: true },
  { name: "April 2023", value: "April 2023", active: false },
]

export const mockSidebarData = [
  {
    sectionTitle: "Authentication and Authorization",
    list: [
      {
        itemTitle: "Groups",
        titleLink: "/admin/auth/groups/",
        addLink: "/admin/auth/groups/add/",
      },
      {
        itemTitle: "Users",
        titleLink: "/admin/auth/users/",
        addLink: "/admin/auth/users/add/",
      },
    ],
  },
  {
    sectionTitle: "LLM Integration",
    list: [
      {
        itemTitle: "Messages",
        titleLink: "/admin/llm/messages/",
        addLink: "/admin/llm/messages/add/",
      },
    ],
  },
]

export const mockBreadcrumbs = [
  { text: "Home", link: "/" },
  { text: "LLM Integration", link: "/admin/llm/" },
  { text: "Messages", link: "/admin/llm/messages/" },
]

export const mockChatMessages = [
  { role: "user", content: "Здравствуйте!" },
  { role: "assistant", content: "Добрый день!" },
  { role: "user", content: "Расскажите что-нибудь интересное" },
  { role: "assistant", content: "Конечно! Вот интересный факт..." },
]

export async function getMockDateFilters() {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve([
        { name: "All dates", value: 0, active: false },
        { name: "April 2025", value: "April 2025", active: false },
        { name: "April 2024", value: "April 2024", active: true },
        { name: "April 2023", value: "April 2023", active: false },
      ])
    }, 1300)
  })
}
