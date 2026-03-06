import mongoose from "mongoose";

const userSchema = new mongoose.Schema(
  {
    chatId: { type: String, unique: true, sparse: true },
    telegramId: { type: Number, default: null },
    firstName: { type: String, default: "" },
    lastName: { type: String, default: "" },
    username: { type: String, default: "" },
    phone: { type: String, default: "" },
    githubToken: { type: String, default: "" },
    dockerUsername: { type: String, default: "" },
    dockerPAT: { type: String, default: "" },
    messageCount: { type: Number, default: 0 },
    password: { type: String, required: true },
  },
  { timestamps: true }
);

export default mongoose.models.User || mongoose.model("User", userSchema);
