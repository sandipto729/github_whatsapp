import CredentialsProvider from "next-auth/providers/credentials";
import dbConnect from "@/app/lib/db";
import User from "@/app/lib/models/User";

export const authOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        await dbConnect();

        const user = await User.findOne({ username: credentials.username });
        if (!user || user.password !== credentials.password) {
          return null;
        }

        return {
          id: user._id.toString(),
          name: user.username,
          username: user.username,
        };
      },
    }),
  ],
  session: {
    strategy: "jwt",
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.username = user.username;
        token.userId = user.id;
      }
      return token;
    },
    async session({ session, token }) {
      session.user.username = token.username;
      session.user.userId = token.userId;
      return session;
    },
  },
  pages: {
    signIn: "/",
  },
  secret: process.env.NEXTAUTH_SECRET,
};
