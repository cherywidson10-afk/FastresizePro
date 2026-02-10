import express from "express";
import multer from "multer";
import { exec } from "child_process";
import fs from "fs";

const app = express();
const upload = multer({ dest: "uploads/" });

// Endpoint pou trete videyo
app.post("/compress", upload.single("video"), (req, res) => {
  if (!req.file) return res.status(400).send("No file uploaded");

  const input = req.file.path;
  const output = `outputs/output-${Date.now()}.mp4`;

  // Kòmand FFmpeg pou resize + compression
  const cmd = `
    ffmpeg -i ${input} 
    -vf scale=1280:-2 
    -c:v libx264 -b:v 1200k -preset veryfast 
    -c:a aac -b:a 96k 
    ${output}
  `;

  exec(cmd, (error) => {
    if (error) {
      console.error(error);
      res.status(500).send("Error processing video");
      fs.unlinkSync(input);
      return;
    }

    // Voye fichye trete a
    res.download(output, () => {
      fs.unlinkSync(input);   // efase upload
      fs.unlinkSync(output);  // efase output
    });
  });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
