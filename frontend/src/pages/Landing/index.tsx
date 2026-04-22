import { NavbarHero } from '@/components/ui/hero-with-video'

export default function LandingPage() {
  return (
    <NavbarHero
      brandName="Docs Agent"
      heroTitle="文档智能体协同中枢"
      heroSubtitle="实时编排 / 协同执行 / 数据闭环"
      heroDescription="统一进入调度中心、审批工作台与监控终端。"
      backgroundImage="https://images.unsplash.com/photo-1451187580459-43490279c0fa?ixlib=rb-4.0.3&auto=format&fit=crop&w=2072&q=80"
    />
  )
}
