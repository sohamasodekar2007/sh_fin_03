import Nav from "@/components/Nav";
import Hero from "@/components/Hero";
import Pipeline from "@/components/Pipeline";
import About from "@/components/About";
import FeatureSlider from "@/components/FeatureSlider";
import WhyCloudCare from "@/components/WhyCloudCare";
import WhatsUnique from "@/components/WhatsUnique";
import Team from "@/components/Team";
import Contact from "@/components/Contact";
import Footer from "@/components/Footer";

export default function LandingPage() {
  return (
    <main>
      <Nav />
      <Hero />
      <Pipeline />
      <About />
      <FeatureSlider />
      <WhyCloudCare />
      <WhatsUnique />
      <Team />
      <Contact />
      <Footer />
    </main>
  );
}
