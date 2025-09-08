# The FRC Book 
When a user asks a relevant question, use this document to help you provide a helpful response.
This "FRC Book" is a guide for FIRST Robotics Competition (FRC) teams, with a focus on design process, strategy, and robot design. It aims to provide a foundational understanding of key concepts without getting bogged down in excessive detail. Here are the key takeaways and actionable advice from the document:

### **Part 1: Process and Design Philosophy**

**The Flow of a Robotics Season:**
*   **Embrace Iteration:** Successful seasons are built on an iterative process. Don't expect to finalize a design immediately after kickoff.
*   **Understand the Game:** The first step is always to thoroughly understand the game manual. Focus on the changes from previous years to speed up the process.
*   **Ask Critical Questions:** Analyze the game to understand scoring, defense, penalties, field layout, and game piece positioning.
*   **Create "Robot CAN" and "Robot WILL" Lists:** Document everything a robot could possibly do, and then narrow it down to what your robot will actually do based on your team's strategy and resources.
*   **Keep an Open Mind:** Be prepared to re-evaluate and change your strategy as you learn more about the game.

**Making Design Decisions:**
*   **Build Consensus:** Aim for consensus in design decisions. If you can't agree, focus on agreeing on the next steps to gather more information.
*   **Use Weighted Decision Matrices:** When consensus is difficult, use a weighted decision matrix to objectively evaluate options.
*   **The Offseason is Crucial:** The offseason is the time to experiment with new and complex mechanisms. During the build season, rely on proven designs and skills.

**Strategic Design and Game Analysis:**
*   **Aim to be an Alliance Captain:** To control your own destiny at a competition, you need to be an alliance captain. This means designing a robot that can consistently earn ranking points.
*   **Be a Good Pick for an Alliance Captain:** If being a captain isn't feasible, focus on being a valuable pick. This often means having a robust and reliable drivetrain and being efficient at a specific task.
*   **Read the Manual (Again):** Re-read the manual a few days after kickoff. You will almost certainly catch things you missed the first time.

### **Part 2: Robot Design**

**Quick CAD Tips:**
*   **Don't Repeat Work:** Use patterns, subassemblies, and configurations to avoid modeling the same thing twice.
*   **Use Keyboard Shortcuts:** Increase your CAD speed by using keyboard shortcuts.
*   **Constrain with Intent:** Use sketch constraints to make your designs more robust and easier to modify.
*   **Utilize Design Libraries:** Use libraries like MKCAD to quickly insert standard parts into your assemblies.

**Intakes:**
*   **Active Wheeled Intakes are Key:** For most games, an active wheeled intake is a reliable choice.
*   **Design for the Game Piece:** The type of intake you design will depend heavily on the game piece.
    *   **Balls:** Use top/bottom rollers.
    *   **Boxes:** Use side rollers with compliant wheels.
    *   **Discs/Unusual Pieces:** These usually require the most prototyping.
*   **Compression is Important:** A good starting point for compression is about half an inch, but this should be prototyped.
*   **More Power is Better:** It's easier to reduce the speed of an intake in code than it is to make a mechanically underpowered intake faster.

**Arms:**
*   **Counterbalance is Your Friend:** Use gas shocks, surgical tubing, or torsion springs to reduce the torque on the arm's motor. This makes the arm faster, more controllable, and less likely to break.
*   **Direct Bolt Gears/Sprockets:** To avoid stripping hubs, bolt gears or sprockets directly to the arm.

**Elevators:**
*   **Reduce Friction:** Use bearings to ensure your elevator stages slide smoothly.
*   **Rigging:**
    *   **Continuous:** The second stage moves at the same time as the first.
    *   **Cascade:** The second stage moves after the first stage has fully extended.
*   **Counterbalance:** Use constant force springs to hold the elevator's position without motor power.

**Shooters:**
*   **Control Variables:** Consistency is key. A shooter that makes the same shot every time is better than one that can shoot from anywhere but is inconsistent.
*   **Flywheel Shooters:**
    *   **Constant Speed:** Use a flywheel to maintain shooter speed between shots.
    *   **Consistent Feeding:** Feed game pieces into the shooter in the same way every time.
*   **Kickers/Punchers/Catapults:** These can be more consistent than flywheel shooters but are often larger, heavier, and slower to reload.